"""Remote profile editor: validates and publishes through REST, never local storage."""

import json
from copy import deepcopy

import httpx
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, TabbedContent, TabPane, TextArea

from poc.adapters.outbound.control_client import ControlClient, RemoteRejected
from poc.domain.primitives import DomainError
from poc.profile_config import with_session_budget


class ProfilesScreen(ModalScreen):
    def __init__(self, client: ControlClient, profiles: list[dict]):
        super().__init__()
        self.client = client
        self.catalog = {
            f"{p['profile_id']}@{p['version']}": p for p in profiles if "definition" in p
        }
        self.definition = None
        self.validated = None
        self.submitted = None
        self.key = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="wizard"):
            yield Label("Perfis de estratégia · cadastrar, duplicar ou criar revisão")
            yield Select(
                [
                    ("Template · Day trade", "DAY_TRADE"),
                    ("Template · Swing", "SWING"),
                    ("Template · Scalping", "SCALPING"),
                ]
                + [
                    (f"{identity} · {p.get('status', '')}", identity)
                    for identity, p in self.catalog.items()
                ],
                value="DAY_TRADE",
                allow_blank=False,
                id="profile-source",
            )
            yield Label("ID do perfil · nome · revisão · par padrão")
            yield Input(placeholder="meu_perfil", id="profile-id")
            yield Input(placeholder="Nome para exibição", id="profile-name")
            yield Input("1", placeholder="Revisão inteira", id="profile-version", type="integer")
            yield Input("ETHUSDT", placeholder="Par padrão", id="profile-symbol")
            yield Select(
                [("Day trade", "DAY_TRADE"), ("Swing", "SWING"), ("Scalping", "SCALPING")],
                value="DAY_TRADE",
                allow_blank=False,
                id="profile-style",
            )
            yield Select(
                [
                    ("Rompimento", "breakout_long_v1"),
                    ("Cruzamento de EMAs", "ema_cross_long_v1"),
                    ("Alinhamento de EMAs", "baseline_v1"),
                ],
                value="breakout_long_v1",
                allow_blank=False,
                id="profile-family",
            )
            yield Static(
                "Parâmetros e instruções orientam o bot. Cada sessão preserva a revisão escolhida. "
                "Escreva objetivos e orientações do JEV em inglês."
            )
            with TabbedContent():
                with TabPane("Parâmetros e instruções"):
                    yield TextArea("", id="profile-parameters", show_line_numbers=True)
                with TabPane("Referência dos campos"):
                    yield TextArea("", id="profile-schema", read_only=True, show_line_numbers=False)
            yield Static(
                "Escolha um template e ajuste os valores; depois valide para revisar a prévia.",
                id="profile-message",
            )
            with Horizontal():
                yield Button("Validar", id="profile-validate")
                yield Button(
                    "Salvar e publicar", variant="success", id="profile-publish", disabled=True
                )
                yield Button("Arquivar", id="profile-archive", disabled=True)
                yield Button("Fechar", id="profile-cancel")

    def on_mount(self):
        self.load_source()

    @on(Select.Changed, "#profile-source")
    def source_changed(self, event):
        if event.value is not Select.NULL:
            self.load_source()

    @work(exclusive=True, group="profile-load", exit_on_error=False)
    async def load_source(self):
        try:
            source = self.query_one("#profile-source", Select).value
            if source in self.catalog:
                record = self.catalog[source]
                definition = with_session_budget(record["definition"])
                definition["profile"]["version"] += 1
                schema = record.get("parameter_schema", {})
            else:
                payload = await self.client.request("GET", f"/v1/profile-template?style={source}")
                definition, schema = payload["definition"], payload["parameter_schema"]
            self.definition = definition
            self.validated = self.submitted = self.key = None
            identity = definition["profile"]
            self.query_one("#profile-style", Select).value = identity["style"]
            self.query_one("#profile-family", Select).value = identity["strategy_family"]
            self.query_one("#profile-id", Input).value = identity["profile_id"]
            self.query_one("#profile-name", Input).value = identity["display_name"]
            self.query_one("#profile-version", Input).value = str(identity["version"])
            self.query_one("#profile-symbol", Input).value = definition["session_defaults"][
                "symbol"
            ]
            self.query_one("#profile-parameters", TextArea).load_text(
                json.dumps(definition["parameters"], indent=2, ensure_ascii=False)
            )
            self.query_one("#profile-schema", TextArea).load_text(
                json.dumps(schema, indent=2, ensure_ascii=False)
            )
            self.query_one("#profile-publish", Button).disabled = True
            self.query_one("#profile-archive", Button).disabled = (
                source not in self.catalog or "manage" not in self.client.scopes
            )
            self.message(
                "Edite o ID para duplicar ou aumente a revisão para evoluir. "
                "Publicar não inicia o bot."
            )
        except (DomainError, httpx.HTTPError, KeyError):
            self.message(
                "Não foi possível carregar o template. "
                "Atualize o serviço de controle e tente novamente."
            )

    def message(self, message):
        self.query_one("#profile-message", Static).update(Text(message))

    @on(Select.Changed, "#profile-family")
    def family_changed(self, event):
        if (
            event.value is Select.NULL
            or self.definition is None
            or event.value != self.query_one("#profile-family", Select).value
        ):
            return
        editor = self.query_one("#profile-parameters", TextArea)
        try:
            p = json.loads(editor.text)
        except ValueError:
            return
        if p["strategy"]["algorithm_version"] == event.value:
            return
        p["strategy"]["algorithm_version"] = event.value
        t = p["strategy"]["technical"]
        t["entry_rule"] = {
            "breakout_long_v1": "PRIOR_HIGH_BREAKOUT",
            "ema_cross_long_v1": "EMA_CROSS",
            "baseline_v1": "EMA_TREND",
        }[event.value]
        breakout = event.value == "breakout_long_v1"
        t["breakout_lookback_candles"] = 8 if breakout else None
        t["breakout_buffer_pct"] = "0.05" if breakout else None
        t["ema_cross_previous_candle_required"] = event.value == "ema_cross_long_v1"
        editor.load_text(json.dumps(p, indent=2, ensure_ascii=False))
        self.validated = None
        self.query_one("#profile-publish", Button).disabled = True
        self.message("Família alterada. Revise as instruções do JEV e valide novamente.")

    def body(self):
        if not self.definition:
            raise DomainError("Carregue um template primeiro.")
        body = deepcopy(self.definition)
        identity = body["profile"]
        identity.update(
            profile_id=self.query_one("#profile-id", Input).value.strip(),
            display_name=self.query_one("#profile-name", Input).value.strip(),
            version=int(self.query_one("#profile-version", Input).value),
            lifecycle_status="DRAFT",
            implementation_status="IMPLEMENTED",
            style=self.query_one("#profile-style", Select).value,
            strategy_family=self.query_one("#profile-family", Select).value,
        )
        body["session_defaults"]["symbol"] = (
            self.query_one("#profile-symbol", Input).value.strip().upper()
        )
        body["parameters"] = json.loads(self.query_one("#profile-parameters", TextArea).text)
        return body

    @on(Button.Pressed, "#profile-validate")
    @work(exclusive=True, group="profile-command", exit_on_error=False)
    async def validate(self):
        try:
            if self.submitted is not None:
                raise DomainError(
                    "Há um envio pendente. Repita Salvar e publicar para consultar o mesmo comando."
                )
            body = self.body()
            result = await self.client.request("POST", "/v1/profiles/validate", body=body)
            self.validated = body
            preview = result["preview"]
            self.message(
                f"Válido · {preview['interval']} / tendência {preview['trend_interval']} · "
                f"posição máxima {preview['maximum_holding_seconds']}s · "
                f"labels {preview['horizon_seconds']}s · "
                f"até {preview['maximum_cycles_per_day_utc']} ciclos/dia UTC. "
                "Limites de IA são por bot/sessão e podem ser editados na seção ai. "
                "Revise e publique; o bot continuará parado."
            )
            self.query_one("#profile-publish", Button).disabled = "manage" not in self.client.scopes
        except (DomainError, httpx.HTTPError, ValueError, KeyError) as error:
            self.validated = None
            self.query_one("#profile-publish", Button).disabled = True
            self.message(f"Validação recusada: {error}")

    @on(Button.Pressed, "#profile-publish")
    @work(exclusive=True, group="profile-command", exit_on_error=False)
    async def publish(self):
        button = self.query_one("#profile-publish", Button)
        button.disabled = True
        try:
            if self.submitted is None:
                if self.validated is None or self.body() != self.validated:
                    raise DomainError("Os valores mudaram; valide novamente antes de publicar.")
                self.submitted = deepcopy(self.validated)
                self.key = self.client.command_key()
            identity = self.submitted["profile"]
            await self.client.request(
                "POST", "/v1/profiles", body=self.submitted, key=self.key + "-register"
            )
            await self.client.request(
                "POST",
                f"/v1/profiles/{identity['profile_id']}/versions/{identity['version']}/publish",
                key=self.key + "-publish",
            )
            self.dismiss(True)
        except (DomainError, httpx.HTTPError, ValueError) as error:
            self.message(
                f"Publicação recusada ou pendente: {error}. Repetir preserva o mesmo comando."
            )
            if isinstance(error, RemoteRejected) and error.status in (400, 409, 422):
                self.submitted = self.key = self.validated = None
            elif self.submitted:
                button.disabled = False

    @on(Button.Pressed, "#profile-archive")
    @work(exclusive=True, group="profile-command", exit_on_error=False)
    async def archive(self):
        try:
            source = self.query_one("#profile-source", Select).value
            record = self.catalog[source]
            await self.client.request(
                "POST",
                f"/v1/profiles/{record['profile_id']}/versions/{record['version']}/archive",
                key=self.client.command_key(),
            )
            self.dismiss(True)
        except (DomainError, httpx.HTTPError, KeyError) as error:
            self.message(f"Não foi possível arquivar: {error}")

    @on(Button.Pressed, "#profile-cancel")
    def cancel(self):
        self.dismiss(None)
