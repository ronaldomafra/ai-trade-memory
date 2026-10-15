"""Textual application. All state and operations cross the REST/WS boundary."""

import json
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from poc.adapters.inbound.tui_charts import CandleChart, spark
from poc.adapters.inbound.tui_presenters import (
    REASONS,
    STRATEGIES,
    cycle_groups,
    cycle_time,
    decision_summary,
    source_summary,
    technical_summary,
    update_source_records,
    when,
)
from poc.adapters.inbound.tui_profiles import ProfilesScreen
from poc.adapters.outbound.clipboard import read_totp_clipboard
from poc.adapters.outbound.control_client import ControlClient, RemoteRejected
from poc.domain.primitives import DomainError


def value(raw, digits=2):
    return "—" if raw is None else f"{Decimal(str(raw)):.{digits}f}"


class TotpInput(Input):
    """Accept one complete pasted code; never truncate or extract digits from other text."""

    class PasteRejected(Message):
        def __init__(self, empty: bool):
            super().__init__()
            self.empty = empty

    def _paste_code(self, text: str) -> None:
        if self.disabled:
            return
        code = "".join(text.split())
        if len(code) == 6 and code.isascii() and code.isdecimal():
            self.value = code
            self.cursor_position = len(code)
        else:
            self.restricted()
            self.post_message(self.PasteRejected(empty=not code))

    def _on_paste(self, event: events.Paste) -> None:
        event.prevent_default()
        event.stop()
        self._paste_code(event.text)

    def action_paste(self) -> None:
        self._paste_code(self.app.clipboard)


class LoginScreen(ModalScreen):
    def __init__(self, client: ControlClient):
        super().__init__()
        self.client = client
        self.challenge = None
        self.challenge_timer = None
        self.challenge_expires_at = None

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Conectar ao core · PAPER ONLY")
            yield Static(Text(self.client.server))
            yield Input(placeholder="Usuário proprietário", id="username", max_length=64)
            yield Input(placeholder="Senha", password=True, id="password", max_length=256)
            yield Checkbox("Somente leitura", id="read-only")
            yield TotpInput(
                placeholder="TOTP de 6 dígitos · colar: Ctrl+Shift+V",
                password=True,
                id="otp",
                restrict=r"[0-9]*",
                max_length=6,
                disabled=True,
            )
            yield Button("Colar código", id="paste-otp", disabled=True)
            yield Static("", id="otp-status")
            yield Static("", id="login-error")
            with Horizontal():
                yield Button("Entrar", variant="success", id="login-submit")
                yield Button("Cancelar", id="login-cancel")

    @on(Button.Pressed, "#login-cancel")
    def cancel(self):
        if self.challenge_timer:
            self.challenge_timer.stop()
        self.dismiss(False)

    @on(Input.Changed, "#otp")
    def otp_changed(self, event: Input.Changed):
        message = f"Código recebido: {len(event.value)}/6 números." if event.value else ""
        self.query_one("#otp-status", Static).update(Text(message))

    @on(TotpInput.PasteRejected)
    def otp_paste_rejected(self, event: TotpInput.PasteRejected):
        message = (
            "Use Ctrl+Shift+V ou botão direito → Colar do terminal. Ctrl+V usa a área interna."
            if event.empty
            else "Colagem recusada: copie somente o código de seis números do autenticador."
        )
        self.query_one("#otp-status", Static).update(Text(message))

    @on(Button.Pressed, "#paste-otp")
    @work(exclusive=True, group="clipboard", exit_on_error=False)
    async def paste_otp(self):
        button = self.query_one("#paste-otp", Button)
        button.disabled = True
        challenge = self.challenge
        try:
            code = await read_totp_clipboard()
            if self.challenge and self.challenge == challenge:
                otp = self.query_one("#otp", TotpInput)
                otp._paste_code(code)
                otp.focus()
        except DomainError as error:
            self.query_one("#otp-status", Static).update(Text(str(error)))
        except (OSError, TimeoutError):
            self.query_one("#otp-status", Static).update(
                Text("Área de transferência indisponível. Use Ctrl+Shift+V no campo do código.")
            )
        finally:
            button.disabled = self.challenge is None

    def expire_login(self):
        if self.challenge is None:
            return
        self.challenge = None
        self.challenge_expires_at = None
        if self.challenge_timer:
            self.challenge_timer.stop()
            self.challenge_timer = None
        otp = self.query_one("#otp", Input)
        otp.value = ""
        otp.disabled = True
        self.query_one("#paste-otp", Button).disabled = True
        for identity in ("#username", "#password", "#read-only"):
            self.query_one(identity).disabled = False
        self.query_one("#login-submit", Button).label = "Entrar"
        self.query_one("#login-error", Static).update(
            Text(
                "O prazo de dois minutos para validar o 2FA expirou. Entre novamente com sua senha."
            )
        )
        self.query_one("#password", Input).focus()

    @on(Button.Pressed, "#login-submit")
    @work(exclusive=True, exit_on_error=False)
    async def submit(self):
        button = self.query_one("#login-submit", Button)
        button.disabled = True
        try:
            if self.challenge is None:
                password = self.query_one("#password", Input)
                try:
                    self.challenge = await self.client.login(
                        self.query_one("#username", Input).value,
                        password.value,
                        self.query_one("#read-only", Checkbox).value,
                    )
                finally:
                    password.value = ""
                self.query_one("#password", Input).disabled = True
                self.query_one("#username", Input).disabled = True
                self.query_one("#read-only", Checkbox).disabled = True
                self.challenge_expires_at = getattr(self.client, "challenge_expires_at", None)
                remaining = (
                    (self.challenge_expires_at - datetime.now(UTC)).total_seconds()
                    if self.challenge_expires_at
                    else 120
                )
                if remaining <= 0:
                    self.expire_login()
                    return
                self.challenge_timer = self.set_timer(remaining, self.expire_login)
                otp = self.query_one("#otp", Input)
                otp.disabled = False
                self.query_one("#paste-otp", Button).disabled = False
                otp.focus()
                button.label = "Validar 2FA"
                self.query_one("#login-error", Static).update(
                    Text("Cole o código com Ctrl+Shift+V no terminal e valide o 2FA.")
                )
            else:
                if self.challenge_expires_at and datetime.now(UTC) >= self.challenge_expires_at:
                    self.expire_login()
                    return
                otp = self.query_one("#otp", Input)
                if len(otp.value) != 6 or not otp.value.isascii() or not otp.value.isdecimal():
                    self.query_one("#login-error", Static).update(
                        Text("Informe os seis números do autenticador antes de validar o 2FA.")
                    )
                    otp.focus()
                    return
                try:
                    await self.client.second_factor(self.challenge, otp.value)
                finally:
                    otp.value = ""
                self.challenge = None
                if self.challenge_timer:
                    self.challenge_timer.stop()
                self.dismiss(True)
        except (DomainError, httpx.HTTPError):
            self.query_one("#login-error", Static).update(
                Text("Falha de conexão ou autenticação. Confira os dados; use um código TOTP novo.")
            )
        finally:
            button.disabled = False


class NewSessionScreen(ModalScreen):
    def __init__(self, client: ControlClient, profiles: list[dict]):
        super().__init__()
        self.client = client
        self.profiles = [p for p in profiles if p.get("status") not in ("DRAFT", "ARCHIVED")]
        self.key = client.command_key()
        self.submitted_body = None
        self.prepared_run = None

    def compose(self) -> ComposeResult:
        profile = self.profiles[0]
        with VerticalScroll(id="wizard"):
            yield Label("Nova sessão · três carteiras virtuais de 100 USDT")
            yield Select(
                [
                    (
                        f"{p['profile_id']} · v{p.get('version', '1')} · "
                        f"{p.get('style', 'legado')}",
                        self.profile_choice(p),
                    )
                    for p in self.profiles
                ],
                value=self.profile_choice(profile),
                allow_blank=False,
                id="profile",
            )
            yield Input(profile["symbol_default"], placeholder="Par Spot USDT", id="symbol")
            yield Input(placeholder="Identificador opcional (novo)", id="new-run")
            yield Label(
                "Pré-configuração · valores monetários como texto JSON · limites IA por bot"
            )
            yield TextArea(
                json.dumps(profile["template"], indent=2), id="overrides", show_line_numbers=True
            )
            yield Input(
                placeholder="Dataset JSONL local (opcional; vazio começa sem dataset)",
                id="initial-dataset",
            )
            yield Static("", id="wizard-error")
            with Horizontal():
                yield Button("Criar e iniciar", variant="success", id="create-session")
                yield Button("Cancelar", id="wizard-cancel")

    @on(Button.Pressed, "#wizard-cancel")
    def cancel(self):
        self.dismiss(None)

    @staticmethod
    def profile_choice(profile):
        return (
            f"{profile['profile_id']}@{profile['version']}"
            if "definition" in profile
            else profile["profile_id"]
        )

    def chosen_profile(self):
        value = self.query_one("#profile", Select).value
        return next(p for p in self.profiles if self.profile_choice(p) == value)

    @on(Select.Changed, "#profile")
    def profile_changed(self, event):
        if event.value is Select.NULL or self.submitted_body is not None:
            return
        profile = self.chosen_profile()
        self.query_one("#overrides", TextArea).load_text(
            json.dumps(profile["template"], indent=2, ensure_ascii=False)
        )
        self.query_one("#symbol", Input).value = profile["symbol_default"]

    @on(Button.Pressed, "#create-session")
    @work(exclusive=True, exit_on_error=False)
    async def create_session(self):
        button = self.query_one("#create-session", Button)
        button.disabled = True
        try:
            if self.submitted_body is None:
                overrides = json.loads(self.query_one("#overrides", TextArea).text)
                if not isinstance(overrides, dict):
                    raise DomainError("Configuração precisa ser um objeto JSON.")
                dataset = self.query_one("#initial-dataset", Input).value.strip()
                identity = await self.client.upload(Path(dataset).expanduser()) if dataset else None
                body = {
                    "profile_id": self.chosen_profile()["profile_id"],
                    "symbol": self.query_one("#symbol", Input).value.strip().upper(),
                    "run_id": self.query_one("#new-run", Input).value.strip() or None,
                    "overrides": overrides,
                    "dataset_id": identity,
                }
                profile = self.chosen_profile()
                if "definition" in profile:
                    body.update(
                        profile_version=int(profile["version"]),
                        profile_hash=profile["profile_hash"],
                    )
                self.submitted_body = body
            response = await self.client.request(
                "POST", "/v1/sessions", body=self.submitted_body, key=self.key
            )
            run = response["session"]["run_id"]
            self.prepared_run = run
            await self.client.request("POST", f"/v1/sessions/{run}/start", key=self.key + "-start")
            self.dismiss(run)
        except (DomainError, httpx.HTTPError, OSError, ValueError) as error:
            self.query_one("#wizard-error", Static).update(
                Text(
                    "Criação/início recusado. Confira perfil, par, JSON e dataset. "
                    "Uma repetição usa o mesmo comando; sessões preparadas aparecem na lista."
                )
            )
            # Keep uncertain requests frozen. Never turn a network retry into new capital.
            if (
                isinstance(error, RemoteRejected)
                and error.status in (400, 409, 422)
                and not self.prepared_run
            ):
                self.submitted_body = None
                self.key = self.client.command_key()
        finally:
            button.disabled = False


class DatasetScreen(ModalScreen):
    def __init__(self, client: ControlClient, run_id: str):
        super().__init__()
        self.client, self.run_id = client, run_id

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(Text("Dataset · " + self.run_id))
            yield Input(placeholder="Arquivo JSONL local para importar", id="dataset-input")
            yield Input(
                placeholder="Arquivo novo para exportar (sem sobrescrever)", id="dataset-output"
            )
            yield Static("Importação somente antes da primeira decisão. Não altera saldos.")
            yield Static("", id="dataset-message")
            with Horizontal():
                yield Button(
                    "Importar", id="dataset-import", disabled="manage" not in self.client.scopes
                )
                yield Button("Exportar", id="dataset-export", variant="success")
                yield Button("Fechar", id="dataset-close")

    @on(Button.Pressed, "#dataset-close")
    def close_dialog(self):
        self.dismiss()

    @on(Button.Pressed, "#dataset-import")
    @on(Button.Pressed, "#dataset-export")
    @work(exclusive=True, exit_on_error=False)
    async def transfer_file(self, event: Button.Pressed):
        event.button.disabled = True
        try:
            if event.button.id == "dataset-import":
                identity = await self.client.upload(
                    Path(self.query_one("#dataset-input", Input).value).expanduser()
                )
                await self.client.request(
                    "POST",
                    f"/v1/sessions/{self.run_id}/learning/import",
                    body={"dataset_id": identity},
                )
                message = "Dataset aceito. Carteiras preservadas."
            else:
                path = self.query_one("#dataset-output", Input).value.strip()
                if not path:
                    raise DomainError("Escolha o arquivo de destino.")
                exported = await self.client.request(
                    "POST", f"/v1/sessions/{self.run_id}/learning/export"
                )
                await self.client.download(exported["dataset_id"], Path(path))
                message = f"Dataset exportado: {exported['sample_count']} exemplos."
            self.query_one("#dataset-message", Static).update(Text(message))
        except (DomainError, OSError, httpx.HTTPError):
            self.query_one("#dataset-message", Static).update(
                Text(
                    "Operação recusada. Confira arquivo, permissão e se a sessão já teve decisões."
                )
            )
        finally:
            event.button.disabled = False


class TradeApp(App):
    TITLE = "ai-trade-memory · PAPER ONLY"
    CSS = """
    Screen { background: #031018; color: #bce8f5; }
    Header { background: #061f2d; color: #31d6ff; }
    Footer { background: #061f2d; }
    #toolbar { height: 3; }
    #sessions { width: 1fr; }
    #toolbar Button { min-width: 10; }
    #connection { height: 2; color: #31d6ff; }
    #profile-status { height: auto; color: #7ca1af; }
    #dashboard-grid { grid-size: 2; grid-columns: 1fr 1fr; grid-gutter: 1; height: auto; }
    #dashboard-grid.narrow { grid-size: 1; grid-columns: 1fr; }
    #sources-grid { grid-size: 2; grid-columns: 1fr 1fr; grid-gutter: 1; height: auto; }
    #sources-grid.narrow { grid-size: 1; grid-columns: 1fr; }
    #balances-grid { grid-size: 2; grid-columns: 1fr 1fr; grid-gutter: 1; height: auto; }
    #balances-grid.narrow { grid-size: 1; grid-columns: 1fr; }
    .panel { border: round #1d9eb7; padding: 0 1; height: auto; min-height: 8; }
    .panel-title { color: #00ff9f; height: 1; text-style: bold; }
    DataTable { height: 9; background: #031018; }
    #wallets { height: 5; }
    #price-chart { height: auto; min-height: 18; }
    #cycle-selector { height: 3; }
    #cycle-summary, #cycle-indicators, #news-summary, #poly-summary, #cycle-progress {
        height: auto;
    }
    #cycle-progress { color: #ffca57; }
    .context-note { height: auto; color: #7ca1af; }
    #equity-chart { height: 5; }
    #ai-details { min-height: 10; height: auto; }
    #learning-details { height: auto; min-height: 20; }
    RichLog { border: round #1d9eb7; }
    #event-filter { height: 3; }
    #config-details { height: 1fr; }
    ModalScreen { align: center middle; background: #000000 65%; }
    #dialog { width: 75; height: auto; max-height: 95%; border: round #31d6ff;
        padding: 1 2; background: #061f2d; }
    #wizard { width: 90%; height: 90%; border: round #31d6ff; padding: 1 2; background: #061f2d; }
    #overrides { height: 20; }
    #profile-parameters, #profile-schema { height: 24; }
    #profile-message { height: auto; color: #ffca57; }
    #wizard Horizontal, #dialog Horizontal { height: 3; }
    #wizard-error, #login-error, #otp-status, #dataset-message { height: auto; color: #ffca57; }
    """
    BINDINGS = [
        ("q", "quit", "Sair"),
        ("r", "refresh", "Atualizar"),
        ("n", "new", "Nova sessão"),
        ("p", "profiles", "Perfis"),
        ("s", "resume", "Iniciar/retomar"),
        ("d", "dataset", "Dataset"),
        ("l", "login", "Login"),
        ("o", "logout", "Logout"),
        ("?", "help", "Ajuda"),
    ]

    def __init__(self, client: ControlClient):
        super().__init__()
        self.client = client
        self.run_id = None
        self.snapshot = None
        self.events = deque(maxlen=1000)
        self.profiles = []
        self.stream_task = None
        self.dirty = False
        self.selected_cycle = None
        self.source_records = {}
        self.cycle_choices = []
        self.live_cycle = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="toolbar"):
            yield Select([], prompt="Selecione uma sessão", id="sessions")
            yield Button("Nova", id="new")
            yield Button("Perfis", id="profiles")
            yield Button("Retomar", id="resume")
            yield Button("Parar", id="stop-engine")
            yield Button("Dataset", id="dataset")
        yield Static("Desconectado · entre para consultar o core", id="connection")
        yield Static("", id="profile-status")
        with TabbedContent():
            with TabPane("Dashboard", id="dashboard"):
                with VerticalScroll():
                    with Vertical(classes="panel", id="price-panel"):
                        yield Static(
                            "CANDLES FECHADOS · OPERAÇÕES SIMULADAS",
                            classes="panel-title",
                            id="price-title",
                        )
                        yield CandleChart(id="price-chart")
                    with Grid(id="balances-grid"):
                        with Vertical(classes="panel", id="wallet-panel"):
                            yield Static("CARTEIRAS · A / B / C", classes="panel-title")
                            yield DataTable(id="wallets")
                        with Vertical(classes="panel", id="equity-panel"):
                            yield Static("PATRIMÔNIO · A / B / C", classes="panel-title")
                            yield Static("Sem observações", id="equity-chart")
                            yield Static("", id="comparison")
                    with Vertical(classes="panel"):
                        yield Static("DECISÕES POR CARTEIRA", classes="panel-title")
                        yield Select(
                            [("Acompanhar último ciclo", "latest")],
                            value="latest",
                            id="cycle-selector",
                            allow_blank=False,
                        )
                        yield Static("", id="cycle-progress")
                        yield Static("Aguardando sessão", id="cycle-summary")
                        yield Static("", id="cycle-indicators")
                    yield Static(
                        "FONTES · últimos registros recebidos, independentes do ciclo selecionado. "
                        "Não indicam influência causal sobre a decisão.",
                        classes="context-note",
                    )
                    with Grid(id="sources-grid"):
                        with Vertical(classes="panel"):
                            yield Static("Aguardando notícia", id="news-summary")
                        with Vertical(classes="panel"):
                            yield Static("Aguardando Polymarket", id="poly-summary")
                    with Vertical(classes="panel"):
                        yield Static("IA / APRENDIZADO / FONTES", classes="panel-title")
                        yield Static("Aguardando sessão", id="ai-details")
                    with Grid(id="dashboard-grid"):
                        with Vertical(classes="panel"):
                            yield Static("POSIÇÕES ABERTAS", classes="panel-title")
                            yield DataTable(id="positions")
                        with Vertical(classes="panel"):
                            yield Static("FILLS SIMULADOS RECENTES", classes="panel-title")
                            yield DataTable(id="fills")
            with TabPane("Decisões", id="decisions-tab"):
                yield DataTable(id="decisions")
            with TabPane("Memória", id="learning-tab"):
                with VerticalScroll():
                    yield Static("Sem memória observada", id="learning-details")
            with TabPane("Eventos", id="events-tab"):
                yield Input(placeholder="Filtrar tipo/componente/mensagem", id="event-filter")
                yield RichLog(id="event-log", max_lines=1000, markup=False, wrap=True)
            with TabPane("Configuração", id="configuration-tab"):
                yield TextArea(
                    "Selecione uma sessão. Configuração persistida é somente leitura.",
                    read_only=True,
                    id="config-details",
                )
        yield Footer()

    def on_mount(self):
        for identity, columns in {
            "wallets": ("Carteira", "Caixa USDT", "Patrimônio", "Retorno %", "PnL", "DD %"),
            "positions": ("Carteira", "Quantidade", "Entrada", "PnL aberto", "Risco"),
            "fills": ("Hora UTC", "Carteira", "Lado", "Quantidade", "Preço", "PnL", "Motivo"),
            "decisions": (
                "Hora UTC",
                "Carteira",
                "Proposta",
                "Validada",
                "Executada",
                "p",
                "Conf.",
                "Motivo",
            ),
        }.items():
            self.query_one("#" + identity, DataTable).add_columns(*columns)
        self.set_interval(2, self.refresh_if_dirty)
        if self.client.access_token:
            self.action_refresh()
        else:
            self.action_login()

    def on_resize(self, event):
        if self.is_mounted:
            self.query_one("#dashboard-grid", Grid).set_class(event.size.width < 110, "narrow")
            self.query_one("#sources-grid", Grid).set_class(event.size.width < 110, "narrow")
            self.query_one("#balances-grid", Grid).set_class(event.size.width < 110, "narrow")

    def connection(self, message: str):
        self.query_one("#connection", Static).update(Text(message))

    def action_login(self):
        self.push_screen(LoginScreen(self.client), self.after_login)

    def after_login(self, accepted):
        if accepted:
            self.action_refresh()

    @work(exclusive=True, group="refresh", exit_on_error=False)
    async def action_refresh(self):
        try:
            records = await self.client.request("GET", "/v1/sessions")
            self.profiles = (await self.client.request("GET", "/v1/profiles"))["profiles"]
            selected = self.query_one("#sessions", Select)
            selected.set_options(
                [
                    (f"{s['run_id']} · {s['symbol']} · {s['profile_id']}", s["run_id"])
                    for s in records["sessions"]
                ]
            )
            if self.run_id and any(s["run_id"] == self.run_id for s in records["sessions"]):
                selected.value = self.run_id
                self.render_snapshot(
                    await self.client.request("GET", f"/v1/sessions/{self.run_id}/snapshot")
                )
                self.follow_session()
            self.query_one("#new", Button).disabled = "manage" not in self.client.scopes
            self.query_one("#resume", Button).disabled = "manage" not in self.client.scopes
            self.query_one("#stop-engine", Button).disabled = "manage" not in self.client.scopes
            if not self.run_id:
                self.connection(f"Conectado · {len(records['sessions'])} sessões · PAPER ONLY")
        except (DomainError, httpx.HTTPError):
            self.connection(
                "Desconectado · dados anteriores não são atuais. Entre ou tente atualizar."
            )

    @on(Select.Changed, "#sessions")
    def select_session(self, event: Select.Changed):
        if event.value is not Select.NULL and event.value != self.run_id:
            self.reset_decision_view()
            self.run_id = str(event.value)
            self.events.clear()
            self.query_one("#event-log", RichLog).clear()
            self.follow_session()

    @work(exclusive=True, group="stream", exit_on_error=False)
    async def follow_session(self):
        run = self.run_id
        try:
            config = await self.client.request("GET", f"/v1/sessions/{run}/configuration")
            self.query_one("#config-details", TextArea).load_text(json.dumps(config, indent=2))
            async for message in self.client.stream(run):
                if self.run_id != run:
                    return
                kind = message["type"]
                if kind == "snapshot":
                    self.render_snapshot(message["snapshot"])
                    after = max(0, message["snapshot"]["event_watermark"] - 100)
                    history = await self.client.request(
                        "GET",
                        f"/v1/sessions/{run}/events?after_seq={after}&limit=100",
                    )
                    for event in history["events"]:
                        self.add_event(event)
                elif kind == "event":
                    self.add_event(message["event"])
                    self.dirty = True
                elif kind == "live":
                    cycle = message["data"].get("cycle") or {}
                    self.live_cycle = cycle
                    self.show_cycle_progress()
                    quote = message["data"].get("quote") or {}
                    health = message["data"].get("health") or {}
                    symbol = self.snapshot["market"]["symbol"] if self.snapshot else ""
                    status = health.get("status", "sem heartbeat")
                    stamp = quote.get("observed_at")
                    age = (
                        max(
                            0,
                            int(
                                (
                                    datetime.now(UTC)
                                    - datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                                ).total_seconds()
                            ),
                        )
                        if stamp
                        else None
                    )
                    freshness = "SEM COTAÇÃO" if age is None else f"cotação {age}s atrás"
                    self.connection(
                        f"Conectado · {run} · {symbol} "
                        f"· bid {value(quote.get('bid'))} · {status} · {freshness} "
                        f"· stream {message['observed_at']}"
                    )
                elif kind == "connected":
                    self.connection(f"Conectado · {run} · PAPER ONLY")
                else:
                    self.connection(
                        f"Reconectando · {run} · dados exibidos podem estar desatualizados"
                    )
        except (DomainError, httpx.HTTPError, KeyError):
            self.connection(f"Sessão {run}: conexão interrompida. Atualize ou entre novamente.")

    async def refresh_if_dirty(self):
        if self.dirty and self.run_id and self.client.access_token:
            self.dirty = False
            try:
                self.render_snapshot(
                    await self.client.request("GET", f"/v1/sessions/{self.run_id}/snapshot")
                )
            except (DomainError, httpx.HTTPError):
                self.connection("Sem snapshot atual · reconectando")

    def render_snapshot(self, snapshot: dict):
        if snapshot.get("run_id") != self.run_id:
            raise DomainError("Snapshot não pertence à sessão selecionada.")
        self.snapshot = snapshot
        profile = snapshot.get("profile") or {}
        admission = snapshot.get("opportunity_admission") or {}
        detail = ""
        if profile:
            detail = (
                f"Perfil {profile['profile_id']} v{profile['version']} · {profile['style']} · "
                f"decisão {profile['interval']} / tendência {profile['trend_interval']}"
            )
            if admission:
                detail += (
                    f" · dia UTC: {admission['admitted']} ciclos admitidos / "
                    f"{admission['filtered']} filtrados"
                )
        self.query_one("#profile-status", Static).update(Text(detail))
        interval = snapshot.get("chart_scope", {}).get("interval", "15m")
        self.query_one("#price-title", Static).update(
            Text(f"CANDLES FECHADOS · {interval} · OPERAÇÕES SIMULADAS")
        )
        wallets = self.query_one("#wallets", DataTable)
        positions = self.query_one("#positions", DataTable)
        wallets.clear()
        positions.clear()
        for wallet in sorted(
            snapshot["portfolios"], key=lambda item: STRATEGIES.get(item["id"], "Z")
        ):
            identity = STRATEGIES.get(wallet["id"], wallet["id"])
            wallets.add_row(
                identity,
                value(wallet["cash_usdt"]),
                value(wallet["equity_usdt"]),
                value(wallet["return_pct"]),
                value(wallet["realized_pnl_usdt"]),
                value(wallet["max_drawdown_pct"]),
            )
            if Decimal(wallet["base_qty"]) > 0:
                positions.add_row(
                    identity,
                    value(wallet["base_qty"], 8),
                    value(wallet.get("entry_fill_price")),
                    value(wallet.get("unrealized_pnl_usdt")),
                    "TRAVADO" if (wallet.get("risk") or {}).get("blocked_until_utc") else "ATIVO",
                )
        fills = self.query_one("#fills", DataTable)
        fills.clear()
        for fill in snapshot.get("recent_fills", []):
            fills.add_row(
                fill["filled_at"][11:19],
                STRATEGIES.get(fill["portfolio_id"], "?"),
                fill["side"],
                value(fill["qty_base"], 8),
                value(fill["fill_price"]),
                value(fill.get("realized_pnl_usdt")),
                Text(REASONS.get(fill.get("trigger"), fill.get("trigger") or "Não informado")),
            )
        table = self.query_one("#decisions", DataTable)
        table.clear()
        for decision in snapshot.get("recent_decisions", []):
            table.add_row(
                decision["decision_at"][11:19],
                STRATEGIES.get(decision["portfolio_id"], "?"),
                decision["proposed_action"],
                decision["approved_action"],
                decision["executed_action"],
                Text(decision.get("probabilities_json") or "—"),
                value(decision.get("confidence"), 3),
                Text(decision["reason_code"]),
            )
        self.render_decision_view()
        self.source_records = update_source_records(snapshot, self.source_records)
        for section, widget in (("news", "news-summary"), ("prediction_markets", "poly-summary")):
            self.query_one("#" + widget, Static).update(
                source_summary(
                    section,
                    self.source_records.get(section),
                    (snapshot.get("external_context") or {}).get(section, {}),
                )
            )
        curves = Text()
        for identity, label in STRATEGIES.items():
            series = [
                item["equity_usdt"]
                for item in snapshot.get("equity_series", [])
                if item["portfolio_id"] == identity
            ]
            curves.append(
                label + " " + spark(series) + "\n",
                style={"A": "cyan", "B": "yellow", "C": "green"}[label],
            )
        self.query_one("#equity-chart", Static).update(curves)
        comparison = snapshot.get("strategy_comparison", {})
        self.query_one("#comparison", Static).update(
            Text(
                f"C−B: {value(comparison.get('c_minus_b_return_pp'))} pp  "
                f"B−A: {value(comparison.get('b_minus_a_return_pp'))} pp"
            )
        )
        cost = snapshot.get("ai_cost", {})
        daily_budget = cost.get("daily_budget")
        budget_text = ""
        if daily_budget:
            limit = (
                f"US$ {daily_budget['max_observed_cost_usd_per_day']}"
                if daily_budget["cost_limit_enabled"]
                else "limite financeiro desativado"
            )
            budget_text = (
                f"IA hoje UTC · este bot: {daily_budget['physical_attempts']}/"
                f"{daily_budget['max_calls_per_day']} chamadas · "
                f"US$ {value(daily_budget['observed_cost_usd'], 6)} / {limit}\n"
            )
        external = snapshot.get("external_context") or {}
        learning = snapshot.get("learning", {})
        latest = snapshot.get("recent_decisions", [])
        news = external.get("news", {})
        predictions = external.get("prediction_markets", {})
        sources = news.get("sources", {})
        responding = sum(
            source.get("status") in ("COMPLETE", "PARTIAL") for source in sources.values()
        )
        last_ai_reason = next(
            (
                row.get("reason_code", "aguardando")
                for row in latest
                if row.get("portfolio_id") in ("JEV_STATIC", "JEV_LEARNING")
            ),
            "aguardando",
        )
        self.query_one("#ai-details", Static).update(
            Text(
                f"Última decisão: {latest[0]['executed_action'] if latest else 'aguardando'}\n"
                f"JEV: {cost.get('physical_calls', 0)} chamadas nesta sessão · {last_ai_reason}\n"
                f"Custo observado: US$ {value(cost.get('total_api_cost_actual'), 6)}\n"
                f"{budget_text}"
                f"Custos desconhecidos: {cost.get('unknown_cost_calls', 0)}\n"
                f"Notícias: {news.get('status', 'UNAVAILABLE')} · "
                f"{len(news.get('items', []))} fatores utilizáveis\n"
                f"Última coleta de notícias: {responding}/{len(sources)} fontes responderam\n"
                f"Polymarket: {predictions.get('status', 'UNAVAILABLE')} · "
                f"{len(predictions.get('items', []))} fatores utilizáveis\n"
                f"Última descoberta Polymarket: "
                f"{predictions.get('discovery', {}).get('status', 'aguardando')}\n"
                f"Exemplos únicos: {learning.get('archived_unique_examples', 0)}\n"
                "Confiança JEV, probabilidades e qualidade da fonte são medidas distintas."
            )
        )
        self.query_one("#learning-details", Static).update(
            Text(
                json.dumps(
                    {
                        "learning": learning,
                        "coverage": comparison.get("coverage"),
                        "external_context": external,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        )

    def reset_decision_view(self):
        self.query_one("#profile-status", Static).update("")
        self.snapshot = None
        self.selected_cycle = None
        self.source_records = {}
        self.cycle_choices = []
        self.live_cycle = None
        self.query_one("#cycle-selector", Select).set_options(
            [("Acompanhar último ciclo", "latest")]
        )
        self.query_one("#cycle-selector", Select).value = "latest"
        for widget in (
            "cycle-summary",
            "cycle-indicators",
            "cycle-progress",
            "news-summary",
            "poly-summary",
        ):
            self.query_one("#" + widget, Static).update(Text("Aguardando dados da sessão."))
        self.query_one("#price-chart", CandleChart).set_candles([])

    @on(Select.Changed, "#cycle-selector")
    def select_cycle(self, event: Select.Changed):
        if (
            event.value is Select.NULL
            or event.value != self.query_one("#cycle-selector", Select).value
        ):
            return
        self.selected_cycle = None if event.value == "latest" else str(event.value)
        self.render_decision_view()

    @on(CandleChart.CycleSelected)
    def chart_cycle_selected(self, event: CandleChart.CycleSelected):
        groups = cycle_groups((self.snapshot or {}).get("recent_decisions", []))
        if event.cycle_id in groups:
            self.query_one("#cycle-selector", Select).value = event.cycle_id
        else:
            self.notify("Ciclo fora do histórico recente de decisões recebido.")

    def render_decision_view(self):
        if not self.snapshot:
            return
        groups = cycle_groups(self.snapshot.get("recent_decisions", []))
        choices = [(identity, cycle_time(rows)) for identity, rows in groups.items()]
        if self.selected_cycle and self.selected_cycle not in groups:
            self.selected_cycle = None
        selector = self.query_one("#cycle-selector", Select)
        if choices != self.cycle_choices:
            self.cycle_choices = choices
            selector.set_options(
                [("Acompanhar último ciclo", "latest")]
                + [(f"Avaliação {when(stamp)}", identity) for identity, stamp in choices]
            )
        wanted = self.selected_cycle or "latest"
        if selector.value != wanted:
            selector.value = wanted
        identity = self.selected_cycle or next(iter(groups), None)
        rows = groups.get(identity, [])
        self.show_cycle_progress()
        self.query_one("#cycle-summary", Static).update(decision_summary(rows))
        self.query_one("#cycle-indicators", Static).update(technical_summary(rows))
        self.query_one("#price-chart", CandleChart).set_records(
            self.snapshot.get("chart_candles", []),
            self.snapshot.get("recent_decisions", []),
            self.snapshot.get("recent_fills", []),
            identity,
        )

    def show_cycle_progress(self):
        groups = cycle_groups((self.snapshot or {}).get("recent_decisions", []))
        newest = next(iter(groups.values()), [])
        complete = {r.get("portfolio_id") for r in newest if r.get("status") == "COMPLETED"}
        current = self.live_cycle or {}
        waiting = bool(newest and set(STRATEGIES) - complete) or (
            current.get("status") == "STARTED" and current.get("cycle_id") not in groups
        )
        self.query_one("#cycle-progress", Static).update(
            Text(
                "Ciclo atual em processamento; aguardando conclusões por carteira."
                if waiting
                else ""
            )
        )

    def add_event(self, event: dict):
        if event.get("run_id") != self.run_id:
            raise DomainError("Evento de outra sessão.")
        if any(previous["event_id"] == event["event_id"] for previous in self.events):
            return
        self.events.append(event)
        text = self.event_text(event)
        if self.query_one("#event-filter", Input).value.casefold() in text.casefold():
            self.query_one("#event-log", RichLog).write(Text(text))

    @staticmethod
    def event_text(event):
        return f"{event['ts'][11:19]} #{event['event_seq']} {event['event_type']} " + json.dumps(
            event["data"], ensure_ascii=False
        )

    @on(Input.Changed, "#event-filter")
    def filter_events(self, event: Input.Changed):
        log = self.query_one("#event-log", RichLog)
        log.clear()
        for record in self.events:
            text = self.event_text(record)
            if event.value.casefold() in text.casefold():
                log.write(Text(text))

    @on(Button.Pressed, "#new")
    def action_new(self):
        if self.profiles and "manage" in self.client.scopes:
            self.push_screen(NewSessionScreen(self.client, self.profiles), self.created_session)

    def created_session(self, run):
        if run:
            self.run_id = run
            self.follow_session()
            self.action_refresh()

    @on(Button.Pressed, "#profiles")
    @work(exclusive=True, group="profile-catalog", exit_on_error=False)
    async def action_profiles(self):
        if not self.client.access_token:
            self.action_login()
            return
        try:
            records = await self.client.request("GET", "/v1/profiles")
            self.push_screen(
                ProfilesScreen(self.client, records["profiles"]),
                lambda changed: self.action_refresh() if changed else None,
            )
        except (DomainError, httpx.HTTPError):
            self.notify("Não foi possível consultar os perfis.")

    @on(Button.Pressed, "#resume")
    @work(exclusive=True, group="lifecycle", exit_on_error=False)
    async def action_resume(self):
        if self.run_id and "manage" in self.client.scopes:
            try:
                await self.client.request(
                    "POST", f"/v1/sessions/{self.run_id}/start", key=self.client.command_key()
                )
                self.connection("Motor iniciado/retomado. Capital e configuração preservados.")
            except (DomainError, httpx.HTTPError):
                self.connection(
                    "Não foi possível iniciar/retomar. Consulte diagnóstico do servidor."
                )

    @on(Button.Pressed, "#dataset")
    def action_dataset(self):
        if self.run_id:
            self.push_screen(DatasetScreen(self.client, self.run_id))

    @on(Button.Pressed, "#stop-engine")
    @work(exclusive=True, group="lifecycle", exit_on_error=False)
    async def action_stop_engine(self):
        if self.run_id and "manage" in self.client.scopes:
            try:
                await self.client.request(
                    "POST", f"/v1/sessions/{self.run_id}/stop", key=self.client.command_key()
                )
                self.connection("Motor parado. Histórico e carteiras preservados.")
                self.action_refresh()
            except (DomainError, httpx.HTTPError):
                self.connection("Não foi possível confirmar a parada. Consulte o status do motor.")

    async def action_logout(self):
        self.workers.cancel_group(self, "stream")
        self.workers.cancel_group(self, "refresh")
        try:
            await self.client.logout()
        except httpx.HTTPError:
            pass
        self.run_id = self.snapshot = None
        self.reset_decision_view()
        self.profiles = []
        self.query_one("#new", Button).disabled = True
        self.query_one("#resume", Button).disabled = True
        self.query_one("#stop-engine", Button).disabled = True
        self.events.clear()
        self.query_one("#sessions", Select).set_options([])
        for name in ("wallets", "positions", "fills", "decisions"):
            self.query_one("#" + name, DataTable).clear()
        self.query_one("#event-log", RichLog).clear()
        self.query_one("#config-details", TextArea).load_text("")
        self.query_one("#price-chart", CandleChart).set_candles([])
        for name in ("ai-details", "learning-details", "comparison", "equity-chart"):
            self.query_one("#" + name, Static).update("")
        self.connection("Logout concluído · motores continuam em execução")

    def action_help(self):
        self.notify(
            "Tab navega; abas mostram decisões, memória, eventos e configuração. "
            "N cria; S retoma; D transfere dataset; R atualiza; Q sai. "
            "Sair não para o motor. Use a CLI/API no servidor para parada explícita.",
            timeout=15,
        )

    async def action_quit(self):
        self.workers.cancel_all()
        try:
            await self.client.logout()
        except httpx.HTTPError:
            pass
        self.exit()

    async def on_unmount(self):
        await self.client.close()
