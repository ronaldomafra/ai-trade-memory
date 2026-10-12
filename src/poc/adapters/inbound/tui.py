"""Textual application. All state and operations cross the REST/WS boundary."""

import json
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
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
from poc.adapters.outbound.control_client import ControlClient, RemoteRejected
from poc.domain.primitives import DomainError

STRATEGIES = {"BASELINE_TECHNICAL": "A", "JEV_STATIC": "B", "JEV_LEARNING": "C"}


def value(raw, digits=2):
    return "—" if raw is None else f"{Decimal(str(raw)):.{digits}f}"


class LoginScreen(ModalScreen):
    def __init__(self, client: ControlClient):
        super().__init__()
        self.client = client
        self.challenge = None

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Conectar ao core · PAPER ONLY")
            yield Static(Text(self.client.server))
            yield Input(placeholder="Usuário proprietário", id="username", max_length=64)
            yield Input(placeholder="Senha", password=True, id="password", max_length=256)
            yield Checkbox("Somente leitura", id="read-only")
            yield Input(
                placeholder="Código TOTP de 6 dígitos",
                password=True,
                id="otp",
                restrict=r"[0-9]*",
                max_length=6,
                disabled=True,
            )
            yield Static("", id="login-error")
            with Horizontal():
                yield Button("Entrar", variant="success", id="login-submit")
                yield Button("Cancelar", id="login-cancel")

    @on(Button.Pressed, "#login-cancel")
    def cancel(self):
        self.dismiss(False)

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
                otp = self.query_one("#otp", Input)
                otp.disabled = False
                otp.focus()
                button.label = "Validar 2FA"
            else:
                otp = self.query_one("#otp", Input)
                try:
                    await self.client.second_factor(self.challenge, otp.value)
                finally:
                    otp.value = ""
                self.challenge = None
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
        self.client, self.profiles = client, profiles
        self.key = client.command_key()
        self.submitted_body = None
        self.prepared_run = None

    def compose(self) -> ComposeResult:
        profile = self.profiles[0]
        with VerticalScroll(id="wizard"):
            yield Label("Nova sessão · três carteiras virtuais de 100 USDT")
            yield Select(
                [(p["profile_id"], p["profile_id"]) for p in self.profiles],
                value=profile["profile_id"],
                allow_blank=False,
                id="profile",
            )
            yield Input(profile["symbol_default"], placeholder="Par Spot USDT", id="symbol")
            yield Input(placeholder="Identificador opcional (novo)", id="new-run")
            yield Label("Pré-configuração da estratégia · valores monetários como texto JSON")
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
                    "profile_id": self.query_one("#profile", Select).value,
                    "symbol": self.query_one("#symbol", Input).value.strip().upper(),
                    "run_id": self.query_one("#new-run", Input).value.strip() or None,
                    "overrides": overrides,
                    "dataset_id": identity,
                }
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
    #dashboard-grid { grid-size: 2; grid-columns: 1fr 1fr; grid-gutter: 1; height: auto; }
    #dashboard-grid.narrow { grid-size: 1; grid-columns: 1fr; }
    .panel { border: round #1d9eb7; padding: 0 1; height: auto; min-height: 8; }
    .panel-title { color: #00ff9f; height: 1; text-style: bold; }
    DataTable { height: 9; background: #031018; }
    #price-chart { height: 13; }
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
    #wizard Horizontal, #dialog Horizontal { height: 3; }
    #wizard-error, #login-error, #dataset-message { height: auto; color: #ffca57; }
    """
    BINDINGS = [
        ("q", "quit", "Sair"),
        ("r", "refresh", "Atualizar"),
        ("n", "new", "Nova sessão"),
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

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="toolbar"):
            yield Select([], prompt="Selecione uma sessão", id="sessions")
            yield Button("Nova", id="new")
            yield Button("Retomar", id="resume")
            yield Button("Dataset", id="dataset")
        yield Static("Desconectado · entre para consultar o core", id="connection")
        with TabbedContent():
            with TabPane("Dashboard", id="dashboard"):
                with VerticalScroll():
                    with Grid(id="dashboard-grid"):
                        with Vertical(classes="panel"):
                            yield Static("CARTEIRAS · A / B / C", classes="panel-title")
                            yield DataTable(id="wallets")
                        with Vertical(classes="panel"):
                            yield Static("CANDLES FECHADOS · 15m", classes="panel-title")
                            yield CandleChart(id="price-chart")
                        with Vertical(classes="panel"):
                            yield Static("PATRIMÔNIO · A / B / C", classes="panel-title")
                            yield Static("Sem observações", id="equity-chart")
                            yield Static("", id="comparison")
                        with Vertical(classes="panel"):
                            yield Static("IA / APRENDIZADO / FONTES", classes="panel-title")
                            yield Static("Aguardando sessão", id="ai-details")
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
            "fills": ("Hora UTC", "Carteira", "Lado", "Quantidade", "Preço", "PnL"),
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
            if not self.run_id:
                self.connection(f"Conectado · {len(records['sessions'])} sessões · PAPER ONLY")
        except (DomainError, httpx.HTTPError):
            self.connection(
                "Desconectado · dados anteriores não são atuais. Entre ou tente atualizar."
            )

    @on(Select.Changed, "#sessions")
    def select_session(self, event: Select.Changed):
        if event.value is not Select.NULL and event.value != self.run_id:
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
        self.query_one("#price-chart", CandleChart).set_candles(snapshot.get("chart_candles", []))
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
        external = snapshot.get("external_context") or {}
        learning = snapshot.get("learning", {})
        latest = snapshot.get("recent_decisions", [])
        self.query_one("#ai-details", Static).update(
            Text(
                f"Última decisão: {latest[0]['executed_action'] if latest else 'aguardando'}\n"
                f"Custo observado: US$ {value(cost.get('total_api_cost_actual'), 6)}\n"
                f"Custos desconhecidos: {cost.get('unknown_cost_calls', 0)}\n"
                f"Notícias: {external.get('news', {}).get('status', 'UNAVAILABLE')}\n"
                "Polymarket: "
                + external.get("prediction_markets", {}).get("status", "UNAVAILABLE")
                + "\n"
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

    async def action_logout(self):
        self.workers.cancel_group(self, "stream")
        self.workers.cancel_group(self, "refresh")
        try:
            await self.client.logout()
        except httpx.HTTPError:
            pass
        self.run_id = self.snapshot = None
        self.profiles = []
        self.query_one("#new", Button).disabled = True
        self.query_one("#resume", Button).disabled = True
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
