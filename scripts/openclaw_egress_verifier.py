#!/usr/bin/env python3
import asyncio
import argparse
import json
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

import httpx
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from rich.console import Console
from rich.table import Table
from rich.live import Live

console = Console()


class ConnectorError(Exception):
    """Raised when a connector cannot produce a usable local proxy."""


class AttrProfile(Dict[str, Any]):
    """Lightweight typed dict-style container for parsed IP profile data."""


class ProxyConnector:
    """Base abstraction that yields a proxy URL usable by httpx."""

    async def start(self) -> Optional[str]:
        return None

    async def stop(self) -> None:
        return None


class DirectConnector(ProxyConnector):
    async def start(self) -> Optional[str]:
        return None


class StaticProxyConnector(ProxyConnector):
    def __init__(self, proxy_url: str):
        self.proxy_url = proxy_url

    async def start(self) -> Optional[str]:
        return self.proxy_url


class LocalPortConnector(ProxyConnector):
    """Treats a local port as an already-running HTTP or SOCKS proxy."""

    def __init__(self, port_text: str):
        self.port_text = validate_port_text(port_text)

    async def start(self) -> Optional[str]:
        console.print(f"[dim]Auto-detecting proxy protocol on local port {self.port_text}...[/]")
        return await test_proxy_protocol(self.port_text)


class SingBoxNodeConnector(ProxyConnector):
    """Generates a temporary sing-box config and uses it as an internal bridge."""

    def __init__(self, node: Dict[str, Any], sing_box_bin: str = "sing-box"):
        self.node = node
        self.sing_box_bin = sing_box_bin
        self.process: Optional[asyncio.subprocess.Process] = None
        self.temp_config_path: Optional[Path] = None
        self.proxy_url: Optional[str] = None

    async def start(self) -> Optional[str]:
        listen_port = find_free_port()
        self.proxy_url = f"socks5://127.0.0.1:{listen_port}"
        config = build_singbox_config(self.node, listen_port)
        warning = self.node.get("_warning")
        if warning:
            console.print(f"[yellow]Warning:[/] {warning}")

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="split-tunnel-",
            delete=False,
            dir="/tmp",
        ) as f:
            json.dump(config, f, indent=2)
            f.flush()
            self.temp_config_path = Path(f.name)

        check_cmd = [self.sing_box_bin, "check", "-c", str(self.temp_config_path)]
        check_proc = await asyncio.create_subprocess_exec(
            *check_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, check_stderr = await check_proc.communicate()
        if check_proc.returncode != 0:
            await self.stop()
            raise ConnectorError(
                f"Generated sing-box config is invalid: {check_stderr.decode().strip() or 'unknown error'}"
            )

        run_cmd = [self.sing_box_bin, "run", "-c", str(self.temp_config_path)]
        self.process = await asyncio.create_subprocess_exec(
            *run_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            await wait_for_local_proxy(self.proxy_url, timeout=15.0, process=self.process)
        except Exception:
            await self.stop()
            raise

        return self.proxy_url

    async def stop(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

        if self.temp_config_path and self.temp_config_path.exists():
            self.temp_config_path.unlink(missing_ok=True)
        self.temp_config_path = None


class AutoPortOrNodeConnector(ProxyConnector):
    """
    Resolves a numeric input in two stages:
    1. Try it as an already-running local HTTP/SOCKS proxy.
    2. If that fails, look up a node profile bound to the same user-facing port.
    """

    def __init__(self, port_text: str, fallback_node: Optional[Dict[str, Any]] = None):
        self.port_text = validate_port_text(port_text)
        self.fallback = SingBoxNodeConnector(fallback_node) if fallback_node else None

    async def start(self) -> Optional[str]:
        try:
            return await LocalPortConnector(self.port_text).start()
        except ConnectorError:
            if not self.fallback:
                raise
            console.print(
                f"[dim]Local port {self.port_text} is not an HTTP/SOCKS proxy. "
                "Falling back to an internal sing-box bridge...[/]"
            )
            return await self.fallback.start()

    async def stop(self) -> None:
        if self.fallback:
            await self.fallback.stop()


class CommandBridgeConnector(ProxyConnector):
    """
    Launches an external bridge/client that exposes a local HTTP/SOCKS endpoint.

    This is the generic path for protocols like Snell, VLESS, Hysteria2, AnyTLS,
    Realm, etc. The script itself does not implement those protocols directly.
    Instead, it starts a user-provided command and waits for a local proxy port
    to become ready, then routes the tests through that local proxy.
    """

    def __init__(
        self,
        command: str,
        proxy_url: str,
        startup_timeout: float = 15.0,
        cwd: Optional[str] = None,
    ):
        self.command = command
        self.proxy_url = proxy_url
        self.startup_timeout = startup_timeout
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None

    async def start(self) -> Optional[str]:
        self.process = await asyncio.create_subprocess_shell(
            self.command,
            cwd=self.cwd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            await wait_for_local_proxy(self.proxy_url, timeout=self.startup_timeout, process=self.process)
        except Exception:
            await self.stop()
            raise
        return self.proxy_url

    async def stop(self) -> None:
        if not self.process:
            return
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None


def parse_proxy_endpoint(endpoint: str) -> Tuple[str, str, int]:
    parsed = httpx.URL(endpoint)
    if not parsed.scheme or not parsed.host or parsed.port is None:
        raise ConnectorError(f"Invalid proxy endpoint: {endpoint}")
    return parsed.scheme, parsed.host, parsed.port


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def build_tls_config(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    enabled = bool(node.get("tls", False) or node.get("server_name") or node.get("reality"))
    if not enabled:
        return None

    tls: Dict[str, Any] = {
        "enabled": True,
        "server_name": node.get("server_name", ""),
        "insecure": bool(node.get("insecure", False)),
    }

    if node.get("alpn"):
        tls["alpn"] = node["alpn"]

    if node.get("utls_fingerprint"):
        tls["utls"] = {
            "enabled": True,
            "fingerprint": node["utls_fingerprint"],
        }

    reality = node.get("reality")
    if isinstance(reality, dict):
        tls["reality"] = {
            "enabled": True,
            "public_key": reality["public_key"],
            "short_id": reality.get("short_id", ""),
        }

    return tls


def build_transport_config(node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    transport = node.get("transport")
    if not transport:
        return None

    transport_type = str(transport).lower()
    if transport_type == "ws":
        cfg: Dict[str, Any] = {
            "type": "ws",
            "path": node.get("path", "/"),
        }
        host = node.get("host")
        headers = dict(node.get("headers", {}))
        if host and "Host" not in headers:
            headers["Host"] = host
        if headers:
            cfg["headers"] = headers
        return cfg

    if transport_type == "grpc":
        return {
            "type": "grpc",
            "service_name": node.get("service_name", ""),
        }

    if transport_type == "http":
        return {
            "type": "http",
            "host": node.get("hosts", []),
            "path": node.get("path", "/"),
        }

    if transport_type == "tcp":
        return {"type": "tcp"}

    raise ConnectorError(f"Unsupported transport for sing-box node: {transport}")


def build_singbox_outbound(node: Dict[str, Any]) -> Dict[str, Any]:
    node_type = str(node.get("type", "")).lower()
    entry_port = node.get("entry_port")
    dial_host = node.get("dial_host")
    dial_port = node.get("dial_port")
    server = dial_host or node.get("server")
    server_port = dial_port or node.get("server_port")

    if entry_port is not None:
        server = "127.0.0.1"
        server_port = int(entry_port)

    if not server or not server_port:
        raise ConnectorError(
            "Node must define either 'server' + 'server_port' or an 'entry_port' for local forwarding."
        )

    outbound: Dict[str, Any] = {
        "type": node_type,
        "tag": "proxy",
        "server": server,
        "server_port": int(server_port),
    }

    if node_type == "shadowsocks":
        outbound["method"] = node["method"]
        outbound["password"] = node["password"]
    elif node_type == "vless":
        outbound["uuid"] = node["uuid"]
        if node.get("flow"):
            outbound["flow"] = node["flow"]
        packet_encoding = node.get("packet_encoding")
        if packet_encoding:
            outbound["packet_encoding"] = packet_encoding
    elif node_type == "hysteria2":
        outbound["password"] = node["password"]
    elif node_type == "anytls":
        outbound["password"] = node["password"]
        outbound["idle_session_check_interval"] = node.get("idle_session_check_interval", "30s")
        outbound["min_idle_session"] = int(node.get("min_idle_session", 0))
    elif node_type == "socks":
        if node.get("username"):
            outbound["username"] = node["username"]
        if node.get("password"):
            outbound["password"] = node["password"]
        if node.get("version"):
            outbound["version"] = node["version"]
    elif node_type == "http":
        if node.get("username"):
            outbound["username"] = node["username"]
        if node.get("password"):
            outbound["password"] = node["password"]
        outbound["path"] = node.get("path", "/")
    else:
        raise ConnectorError(
            f"Unsupported automatic protocol '{node_type}'. "
            "Current built-in engine supports: shadowsocks, vless, hysteria2, anytls, socks, http."
        )

    tls = build_tls_config(node)
    if tls:
        outbound["tls"] = tls

    transport = build_transport_config(node)
    if transport:
        outbound["transport"] = transport

    return outbound


def build_singbox_config(node: Dict[str, Any], listen_port: int) -> Dict[str, Any]:
    outbound = build_singbox_outbound(node)
    return {
        "log": {
            "disabled": True,
        },
        "inbounds": [
            {
                "type": "socks",
                "tag": "local-socks",
                "listen": "127.0.0.1",
                "listen_port": listen_port,
            }
        ],
        "outbounds": [
            outbound,
            {
                "type": "direct",
                "tag": "direct",
            },
            {
                "type": "block",
                "tag": "block",
            },
        ],
        "route": {
            "final": "proxy",
        },
    }


def load_nodes_config(config_path: Path) -> List[Dict[str, Any]]:
    if not config_path.is_file():
        return []

    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        raise ConnectorError(f"Failed to parse node config '{config_path}': {e}") from e

    nodes = config.get("nodes", [])
    if not isinstance(nodes, list):
        raise ConnectorError(f"Node config '{config_path}' must contain a [[nodes]] array")
    return nodes


def find_node(nodes: List[Dict[str, Any]], selector: str) -> Optional[Dict[str, Any]]:
    selector_text = str(selector).strip()
    for node in nodes:
        if str(node.get("name", "")).strip() == selector_text:
            return node

        aliases = node.get("match", [])
        if isinstance(aliases, list) and selector_text in [str(item) for item in aliases]:
            return node

        match_port = node.get("match_port")
        if match_port is not None and str(match_port) == selector_text:
            return node

        entry_port = node.get("entry_port")
        if entry_port is not None and str(entry_port) == selector_text:
            return node

    return None


def parse_host_port(value: str) -> Tuple[str, int]:
    text = str(value).strip()
    if text.startswith("[") and "]:" in text:
        host, port_text = text[1:].rsplit("]:", 1)
        return host, int(port_text)

    if text.count(":") >= 2:
        host, port_text = text.rsplit(":", 1)
        return host, int(port_text)

    host, port_text = text.rsplit(":", 1)
    return host, int(port_text)


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1", "0.0.0.0", "::"}


def load_structured_config(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text())
        if path.suffix.lower() in {".toml", ".tml"}:
            with open(path, "rb") as f:
                return tomllib.load(f)
    except Exception:
        return None
    return None


def discover_realm_endpoints() -> Dict[int, Dict[str, Any]]:
    candidates = list(Path("/etc").rglob("*realm*.json")) + list(Path("/etc").rglob("*realm*.toml"))
    endpoints: Dict[int, Dict[str, Any]] = {}
    for path in candidates:
        config = load_structured_config(path)
        if not config:
            continue

        for endpoint in config.get("endpoints", []):
            listen = endpoint.get("listen")
            remote = endpoint.get("remote")
            if not listen or not remote:
                continue
            try:
                _, listen_port = parse_host_port(listen)
                remote_host, remote_port = parse_host_port(remote)
            except Exception:
                continue

            endpoints[listen_port] = {
                "type": "realm",
                "source": str(path),
                "listen": listen,
                "remote": remote,
                "remote_host": remote_host,
                "remote_port": remote_port,
            }
    return endpoints


def discover_singbox_inbounds() -> Dict[int, Dict[str, Any]]:
    patterns = [
        "*sing*.json",
        "*sing*.toml",
        "*box*.json",
        "*box*.toml",
        "*vless*.json",
        "*vless*.toml",
    ]
    candidates: List[Path] = []
    etc_path = Path("/etc")
    for pattern in patterns:
        candidates.extend(etc_path.rglob(pattern))

    inbounds: Dict[int, Dict[str, Any]] = {}
    for path in candidates:
        config = load_structured_config(path)
        if not config:
            continue

        for inbound in config.get("inbounds", []):
            listen_port = inbound.get("listen_port")
            if not listen_port:
                continue
            inbound_copy = dict(inbound)
            inbound_copy["_source"] = str(path)
            inbounds[int(listen_port)] = inbound_copy
    return inbounds


def build_node_from_inbound(inbound: Dict[str, Any], connect_port: int) -> Optional[Dict[str, Any]]:
    inbound_type = str(inbound.get("type", "")).lower()
    node: Dict[str, Any] = {
        "name": f"derived-{inbound_type}-{connect_port}",
        "match_port": connect_port,
        "entry_port": connect_port,
        "_derived_from": inbound.get("_source"),
    }

    if inbound_type == "hysteria2":
        users = inbound.get("users", [])
        if not users:
            return None
        node.update(
            {
                "type": "hysteria2",
                "password": users[0]["password"],
                "tls": True,
                "insecure": True,
            }
        )
        tls_cfg = inbound.get("tls", {})
        if isinstance(tls_cfg, dict) and tls_cfg.get("server_name"):
            node["server_name"] = tls_cfg["server_name"]
        else:
            node["_warning"] = (
                "Auto-derived Hysteria2 node has no server_name/SNI. "
                "If requests fail, define this port explicitly in nodes.toml."
            )
        return node

    if inbound_type == "shadowsocks":
        users = inbound.get("users", [])
        if users:
            user = users[0]
            password = user.get("password")
            method = user.get("method", inbound.get("method"))
        else:
            password = inbound.get("password")
            method = inbound.get("method")
        if not password or not method:
            return None
        node.update(
            {
                "type": "shadowsocks",
                "method": method,
                "password": password,
            }
        )
        return node

    if inbound_type == "vless":
        users = inbound.get("users", [])
        if not users:
            return None
        user = users[0]
        tls_cfg = inbound.get("tls", {})
        transport = inbound.get("transport", {})
        node.update(
            {
                "type": "vless",
                "uuid": user["uuid"],
                "flow": user.get("flow", ""),
                "tls": bool(tls_cfg),
                "insecure": True if tls_cfg else False,
            }
        )
        if isinstance(tls_cfg, dict) and tls_cfg.get("server_name"):
            node["server_name"] = tls_cfg["server_name"]
        if transport.get("type"):
            node["transport"] = transport["type"]
        if transport.get("path"):
            node["path"] = transport["path"]
        if transport.get("service_name"):
            node["service_name"] = transport["service_name"]
        return node

    return None


def find_local_inbound_node(
    selector: str,
    singbox_inbounds: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not str(selector).isdigit():
        return None

    inbound = singbox_inbounds.get(int(selector))
    if not inbound:
        return None

    return build_node_from_inbound(inbound, connect_port=int(selector))


def find_node_by_remote(nodes: List[Dict[str, Any]], host: str, port: int) -> Optional[Dict[str, Any]]:
    remote_text = f"{host}:{port}"
    for node in nodes:
        if str(node.get("server", "")).strip() == host and int(node.get("server_port", 0) or 0) == port:
            return dict(node)

        remote_matches = node.get("remote_match", [])
        if isinstance(remote_matches, list) and remote_text in [str(item) for item in remote_matches]:
            return dict(node)

    return None


def rewrite_node_for_local_entry(node: Dict[str, Any], local_port: int) -> Dict[str, Any]:
    rewritten = dict(node)
    rewritten["entry_port"] = local_port
    rewritten["match_port"] = local_port
    return rewritten


def resolve_forwarded_node(
    selector: str,
    nodes: List[Dict[str, Any]],
    relay_endpoints: Dict[int, Dict[str, Any]],
    singbox_inbounds: Dict[int, Dict[str, Any]],
    max_depth: int = 4,
) -> Optional[Dict[str, Any]]:
    current_port = int(selector)
    seen: set[int] = set()

    for _ in range(max_depth):
        if current_port in seen:
            break
        seen.add(current_port)

        relay = relay_endpoints.get(current_port)
        if not relay:
            return None

        remote_host = relay["remote_host"]
        remote_port = int(relay["remote_port"])

        if is_loopback_host(remote_host):
            inbound = singbox_inbounds.get(remote_port)
            if inbound:
                derived = build_node_from_inbound(inbound, connect_port=int(selector))
                if derived:
                    return derived

            current_port = remote_port
            continue

        matched_node = find_node_by_remote(nodes, remote_host, remote_port)
        if matched_node:
            return rewrite_node_for_local_entry(matched_node, int(selector))

        return None

    return None


async def wait_for_local_proxy(
    endpoint: str,
    timeout: float = 15.0,
    process: Optional[asyncio.subprocess.Process] = None,
) -> None:
    _, host, port = parse_proxy_endpoint(endpoint)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while loop.time() < deadline:
        if process and process.returncode is not None:
            raise ConnectorError("Bridge command exited before local proxy became ready.")

        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            await asyncio.sleep(0.25)

    raise ConnectorError(f"Timed out waiting for local proxy at {host}:{port}")


def build_connector(
    args: argparse.Namespace,
    nodes: List[Dict[str, Any]],
    relay_endpoints: Dict[int, Dict[str, Any]],
    singbox_inbounds: Dict[int, Dict[str, Any]],
) -> ProxyConnector:
    target_value = args.proxy or args.target
    bridge_command = args.bridge_command
    bridge_proxy = args.bridge_proxy

    if bridge_command:
        if not bridge_proxy:
            raise ConnectorError("--bridge-command requires --bridge-proxy")
        return CommandBridgeConnector(
            command=bridge_command,
            proxy_url=bridge_proxy,
            startup_timeout=args.bridge_timeout,
            cwd=args.bridge_cwd,
        )

    if not target_value or target_value == "direct":
        return DirectConnector()

    if "://" in target_value:
        return StaticProxyConnector(target_value)

    if target_value.isdigit():
        fallback_node = find_node(nodes, target_value)
        if not fallback_node:
            fallback_node = find_local_inbound_node(target_value, singbox_inbounds)
        if not fallback_node:
            fallback_node = resolve_forwarded_node(
                target_value,
                nodes,
                relay_endpoints,
                singbox_inbounds,
            )
        return AutoPortOrNodeConnector(target_value, fallback_node=fallback_node)

    node = find_node(nodes, target_value)
    if node:
        return SingBoxNodeConnector(node)

    raise ConnectorError(
        f"Unknown proxy or node selector '{target_value}'. "
        "Use a local proxy URL/port, or define a matching node in nodes.toml."
    )


def find_direct_ip_matches(results: List[Tuple[str, str, str]]) -> List[str]:
    matches: List[str] = []
    for result_ip, _, _ in results:
        if result_ip and not any(
            marker in result_ip for marker in ["Pending", "Error", "Timeout", "HTTP ", "Request Error", "Path not found"]
        ):
            if "." in result_ip or ":" in result_ip:
                matches.append(result_ip)
    return matches


def summarize_exit_ip(results: List[Tuple[str, str, str]]) -> Tuple[Optional[str], bool]:
    ips = find_direct_ip_matches(results)
    if not ips:
        return None, False

    counts = Counter(ips)
    top_ip, top_count = counts.most_common(1)[0]
    return top_ip, top_count == len(ips)


def is_ip_like(value: str) -> bool:
    return bool(value) and ("." in value or ":" in value)


def parse_attr(attr: str) -> Tuple[str, Optional[int], Optional[int]]:
    text = str(attr).strip()
    if " :: " in text:
        parts = text.split(" :: ")
        if len(parts) == 3:
            attr_type = parts[0].strip()
            score = int(parts[1]) if parts[1].isdigit() else None
            confidence = int(parts[2]) if parts[2].isdigit() else None
            return attr_type, score, confidence

    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1]), None
    return text, None, None


def parse_attr_profile(attr: str) -> AttrProfile:
    attr_type, score, confidence = parse_attr(attr)
    return AttrProfile(
        type_label=attr_type,
        primary_type=attr_type.split(", ", 1)[0].strip() if attr_type else "Unknown",
        score=score,
        confidence=confidence,
    )


def map_kind_to_group(kind: str) -> str:
    if kind in {"isp", "mobile"}:
        return "residential"
    if kind in {"hosting", "proxy", "vpn", "tor", "business"}:
        return "non_residential"
    return "unknown"


def primary_attr_type(attr: str) -> str:
    profile = parse_attr_profile(attr)
    return str(profile["primary_type"])


def classify_residential_status(attr: str) -> str:
    attr_type = primary_attr_type(attr)
    _, purity, _ = parse_attr(attr)
    if attr_type in {"ISP", "Mobile"} and (purity is None or purity >= 70):
        return "is 家宽IP"
    if attr_type in {"Hosting", "VPN", "Proxy", "Tor"}:
        return "is not 家宽IP"
    if attr_type == "Business" and purity is not None and purity < 70:
        return "is not 家宽IP"
    if attr_type in {"Unknown", "-", ""}:
        return "无法判断"
    return "可能是家宽IP"


def build_ip_rollup(results: List[Tuple[str, str, str]]) -> List[Tuple[str, str]]:
    grouped: Dict[str, str] = {}
    for result_ip, _, attr in results:
        if not is_ip_like(result_ip):
            continue
        grouped.setdefault(result_ip, attr)

    ordered = sorted(grouped.items(), key=lambda item: item[0])
    return [(ip, attr) for ip, attr in ordered]


def clamp_score(value: Optional[int]) -> int:
    if value is None:
        return 50
    return max(0, min(100, value))


def build_score_bar(attr: str, width: int = 10) -> str:
    attr_type = primary_attr_type(attr)
    _, purity, _ = parse_attr(attr)
    score = clamp_score(purity)
    unit = "▮"

    def paint(units: List[str]) -> str:
        return " ".join(units)

    base_green_units = round(width * score / 100)
    base_green_units = max(0, min(width, base_green_units))
    erosion_units = width - base_green_units

    if attr_type in {"ISP", "Mobile"}:
        units = [f"[green]{unit}[/]"] * base_green_units
        units += [f"[red]{unit}[/]"] * erosion_units
        return paint(units)

    if attr_type in {"Hosting", "VPN", "Proxy", "Tor"}:
        amber_units = max(0, round(erosion_units * 0.2))
        red_units = erosion_units - amber_units
        units = [f"[green]{unit}[/]"] * base_green_units
        units += [f"[yellow]{unit}[/]"] * amber_units
        units += [f"[red]{unit}[/]"] * red_units
        return paint(units)

    if attr_type == "Business":
        grey_units = max(0, round(erosion_units * 0.3))
        amber_units = erosion_units - grey_units
        units = [f"[green]{unit}[/]"] * base_green_units
        units += [f"[dim]{unit}[/]"] * grey_units
        units += [f"[yellow]{unit}[/]"] * amber_units
        return paint(units)

    grey_units = erosion_units
    units = [f"[green]{unit}[/]"] * base_green_units
    units += [f"[dim]{unit}[/]"] * grey_units
    return paint(units)


def build_assessment_label(attr: str) -> str:
    attr_type, purity, confidence = parse_attr(attr)
    if attr_type in {"", "-", "Unknown"}:
        return "Unknown Score: ?"
    if purity is None:
        return f"{attr_type} Score: ?"
    if confidence is None:
        return f"{attr_type} Score: {purity}"
    return f"{attr_type} Score: {purity}({confidence}%)"


def build_type_label(attr: str) -> str:
    profile = parse_attr_profile(attr)
    attr_type = str(profile["type_label"])
    if not attr_type:
        return "Unknown"
    return attr_type


def build_score_label(attr: str) -> str:
    profile = parse_attr_profile(attr)
    purity = profile["score"]
    confidence = profile["confidence"]
    if purity is None:
        return "?"
    if confidence is None:
        return str(purity)
    return f"{purity}({confidence}%)"


def score_risk_band(score: Optional[int]) -> Tuple[str, str]:
    if score is None:
        return "Unknown Risk", "yellow"
    if score >= 85:
        return "Low Risk", "green"
    if score >= 70:
        return "Moderate Risk", "yellow"
    if score >= 50:
        return "Elevated Risk", "orange3"
    if score >= 30:
        return "High Risk", "red"
    return "Critical Risk", "bright_red"


def colorize_score_label(attr: str) -> str:
    _, purity, _ = parse_attr(attr)
    if purity is None:
        return "[yellow]? Unknown Risk[/]"
    risk_text, color = score_risk_band(purity)
    text = f"{purity} {risk_text}"
    return f"[{color}]{text}[/]"

async def test_proxy_protocol(port: str) -> str:
    """Attempts to auto-detect if the port is HTTP or SOCKS5."""
    try:
        # Try SOCKS5 first
        proxy_url = f"socks5://127.0.0.1:{port}"
        async with httpx.AsyncClient(proxy=proxy_url, verify=False, trust_env=False) as client:
            resp = await client.get("http://1.1.1.1", timeout=3.0)
            if resp.status_code:
                return proxy_url
    except Exception:
        pass
        
    try:
        # Try HTTP proxy
        proxy_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(proxy=proxy_url, verify=False, trust_env=False) as client:
            resp = await client.get("http://1.1.1.1", timeout=3.0)
            if resp.status_code:
                return proxy_url
    except Exception:
        pass
        
    raise ConnectorError(
        f"Local port {port} did not respond as a SOCKS5 or HTTP proxy."
    )


def validate_port_text(port_text: str) -> str:
    if not port_text.isdigit():
        raise ConnectorError(f"Proxy port must be numeric, got: {port_text}")
    port = int(port_text)
    if port < 1 or port > 65535:
        raise ConnectorError(f"Proxy port out of range: {port_text}")
    return port_text

async def analyze_ip(ip: str) -> Tuple[str, str, str]:
    """Queries multiple APIs to determine Geolocation, Score, and Attribute."""
    evidence: List[Tuple[str, int]] = []
    source_votes: List[str] = []
    
    # Fire all APIs concurrently
    async def get_ip_api():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=5.0, trust_env=False) as c:
                r = await c.get(f"http://ip-api.com/json/{ip}?fields=proxy,hosting,mobile,countryCode,city,isp")
                if r.status_code == 200:
                    d = r.json()
                    source_vote = None
                    if d.get('proxy'):
                        evidence.append(("proxy", 45))
                        source_vote = "proxy"
                    if d.get('hosting'):
                        evidence.append(("hosting", 35))
                        if source_vote is None:
                            source_vote = "hosting"
                    if d.get('mobile'):
                        evidence.append(("mobile", 35))
                        if source_vote is None:
                            source_vote = "mobile"
                    if not d.get('hosting') and not d.get('proxy') and not d.get('mobile'):
                        evidence.append(("isp", 25))
                        source_vote = "isp"
                    if source_vote:
                        source_votes.append(source_vote)
                    return d
        except Exception: pass
        return None

    async def get_ipapi_is():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=5.0, trust_env=False) as c:
                r = await c.get(f"https://api.ipapi.is/?q={ip}")
                if r.status_code == 200:
                    d = r.json()
                    source_vote = None
                    if d.get('is_datacenter'):
                        evidence.append(("hosting", 40))
                    if d.get('is_tor'):
                        evidence.append(("tor", 55))
                        source_vote = "tor"
                    elif d.get('is_vpn'):
                        evidence.append(("vpn", 50))
                        source_vote = "vpn"
                    elif d.get('is_proxy'):
                        evidence.append(("proxy", 45))
                        source_vote = "proxy"
                    if d.get('is_mobile'):
                        evidence.append(("mobile", 35))
                        if source_vote is None and not d.get('is_datacenter'):
                            source_vote = "mobile"
                    if not d.get('is_datacenter') and not d.get('is_proxy') and not d.get('is_vpn') and not d.get('is_tor'):
                        evidence.append(("isp", 20))
                        if source_vote is None and not d.get('is_mobile'):
                            source_vote = "isp"
                    elif d.get('is_datacenter') and source_vote is None:
                        source_vote = "hosting"
                    if source_vote:
                        source_votes.append(source_vote)
                    return d
        except Exception: pass
        return None
        
    async def get_ipwhois():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=5.0, trust_env=False) as c:
                r = await c.get(f"https://ipwho.is/{ip}")
                if r.status_code == 200: return r.json()
        except Exception: pass
        return None

    async def get_ipinfo():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=5.0, trust_env=False) as c:
                r = await c.get(f"https://ipinfo.io/{ip}/json")
                if r.status_code == 200:
                    d = r.json()
                    org = d.get('org', '').lower()
                    if any(x in org for x in ['hosting', 'datacenter', 'cloud', 'server']):
                        evidence.append(("hosting", 20))
                        source_votes.append("hosting")
                    elif any(x in org for x in ['wireless', 'broadband', 'fiber', 'telecom', 'communications']):
                        evidence.append(("isp", 10))
                        source_votes.append("isp")
                    return d
        except Exception: pass
        return None

    async def get_ipapi_co():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=5.0, trust_env=False) as c:
                r = await c.get(f"https://ipapi.co/{ip}/json/")
                if r.status_code == 200:
                    d = r.json()
                    if not d.get('error'):
                        # ipapi.co doesn't directly flag hosting, but we can look at ASN
                        org = d.get('org', '').lower()
                        if any(x in org for x in ['hosting', 'datacenter', 'cloud']):
                            evidence.append(("hosting", 15))
                            source_votes.append("hosting")
                        elif any(x in org for x in ['wireless', 'broadband', 'fiber', 'telecom', 'communications']):
                            evidence.append(("isp", 10))
                            source_votes.append("isp")
                        return d
        except Exception: pass
        return None

    async def get_ip2location():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=6.0, trust_env=False) as c:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
                r = await c.get(f"https://www.ip2location.com/{ip}", headers=headers)
                if r.status_code == 200:
                    import re
                    # Look for Usage Type
                    m = re.search(r'Usage Type</th>\s*<td.*?>(.*?)</td>', r.text, re.S)
                    if m:
                        usage = m.group(1).upper()
                        if "DCH" in usage:
                            evidence.append(("hosting", 25))
                            source_votes.append("hosting")
                        elif "RES" in usage:
                            evidence.append(("isp", 20))
                            source_votes.append("isp")
                        elif "MOB" in usage:
                            evidence.append(("mobile", 30))
                            source_votes.append("mobile")
                        elif "COM" in usage:
                            evidence.append(("business", 20))
                            source_votes.append("business")
                    return {"ip2location": True}
        except Exception: pass
        return None

    async def get_scamalytics():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=5.0, trust_env=False) as c:
                r = await c.get(f"https://scamalytics.com/ip/{ip}", headers={"User-Agent": "Mozilla/5.0"})
                if "Attention Required" in r.text or "Cloudflare" in r.text or r.status_code == 403:
                    return None
                import re
                m = re.search(r'Fraud Score: (\d+)', r.text)
                if m:
                    fraud_score = int(m.group(1))
                    if fraud_score >= 80:
                        evidence.append(("vpn", 25))
                        source_votes.append("vpn")
                    elif fraud_score >= 50:
                        evidence.append(("hosting", 15))
                        source_votes.append("hosting")
        except Exception: pass
        return None

    async def get_proxycheck():
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=5.0, trust_env=False) as c:
                r = await c.get(f"http://proxycheck.io/v2/{ip}?vpn=1&asn=1")
                if r.status_code == 200:
                    d = r.json()
                    if d.get("status") == "ok":
                        ip_info = d.get(ip, {})
                        source_vote = None
                        if ip_info.get("proxy") == "yes":
                            source_vote = "proxy"
                        ip_type = ip_info.get("type", "")
                        if ip_type == "Business":
                            evidence.append(("business", 15))
                            if source_vote is None:
                                source_vote = "business"
                        elif ip_type == "VPN":
                            evidence.append(("vpn", 35))
                            source_vote = "vpn"
                        elif ip_info.get("proxy") == "yes":
                            evidence.append(("proxy", 30))
                            source_vote = "proxy"
                        if source_vote:
                            source_votes.append(source_vote)
        except Exception: pass
        return None

    # Run tasks
    res = await asyncio.gather(
        get_ip_api(), get_ipapi_is(), get_ipwhois(), 
        get_ipinfo(), get_ipapi_co(), get_ip2location(),
        get_scamalytics(), get_proxycheck()
    )
    
    # City abbreviation mapping
    CITY_MAP = {
        "Los Angeles": "LAX", "New York": "NYC", "San Francisco": "SFO",
        "Hong Kong": "HK", "Tokyo": "HND", "London": "LDN",
        "Singapore": "SIN", "San Jose": "SJC", "Seattle": "SEA",
        "Chicago": "ORD", "Amsterdam": "AMS", "Frankfurt": "FRA",
        "Paris": "CDG", "Seoul": "ICN"
    }

    # Geolocation & ISP Extraction
    geo_parts = []
    isp = "Unknown"
    for r in res[:5]: # ip-api, ipapi.is, ipwhois, ipinfo, ipapi.co
        if r and isinstance(r, dict):
            cc = r.get('countryCode', r.get('country_code', r.get('country', r.get('location', {}).get('country_code', ''))))
            city = r.get('city', r.get('location', {}).get('city', ''))
            city_abbr = CITY_MAP.get(city, city)
            if cc and city_abbr and not geo_parts: geo_parts = [cc, city_abbr]
            current_isp = r.get('isp', r.get('org', r.get('connection', {}).get('isp', '')))
            if current_isp and isp == "Unknown": isp = current_isp
    
    full_geo = f"{' '.join(geo_parts)} {isp}".strip() if geo_parts else f"{isp}"
            
    # Weighted evidence model: avoid letting a single source collapse the score to 0.
    totals = Counter()
    for kind, weight in evidence:
        totals[kind] += weight

    residential_total = totals["isp"] + totals["mobile"]
    non_residential_total = totals["hosting"] + totals["proxy"] + totals["vpn"] + totals["tor"] + totals["business"]

    if totals["tor"] >= max(totals["vpn"], totals["proxy"], totals["hosting"], totals["business"], residential_total) and totals["tor"] >= 45:
        primary_type = "Tor"
    elif totals["vpn"] >= max(totals["tor"], totals["proxy"], totals["hosting"], totals["business"], residential_total) and totals["vpn"] >= 40:
        primary_type = "VPN"
    elif totals["proxy"] >= max(totals["tor"], totals["vpn"], totals["hosting"], totals["business"], residential_total) and totals["proxy"] >= 35:
        primary_type = "Proxy"
    elif totals["hosting"] >= max(totals["proxy"], totals["business"], residential_total) and totals["hosting"] >= 35:
        primary_type = "Hosting"
    elif totals["mobile"] >= totals["isp"] and totals["mobile"] >= 35:
        primary_type = "Mobile"
    elif residential_total >= max(totals["proxy"], totals["vpn"], totals["tor"], totals["hosting"], totals["business"]) and residential_total >= 25:
        primary_type = "ISP"
    elif totals["business"] >= 20:
        primary_type = "Business"
    else:
        primary_type = "Unknown"

    label_map = {
        "isp": "ISP",
        "mobile": "Mobile",
        "hosting": "Hosting",
        "proxy": "Proxy",
        "vpn": "VPN",
        "tor": "Tor",
        "business": "Business",
    }
    ranked_types = sorted(
        ((kind, weight) for kind, weight in totals.items() if weight > 0),
        key=lambda item: (-item[1], item[0]),
    )
    all_labels = [label_map[kind] for kind, _ in ranked_types]
    if not all_labels:
        all_labels = [primary_type]

    total_weight = residential_total + non_residential_total
    if total_weight == 0:
        purity = 50
    elif primary_type in {"ISP", "Mobile"}:
        purity = int(100 * residential_total / total_weight)
    elif primary_type == "Business":
        purity = int(100 * totals["business"] / total_weight)
    elif primary_type == "Hosting":
        purity = int(100 * totals["hosting"] / total_weight)
    elif primary_type == "Proxy":
        purity = int(100 * totals["proxy"] / total_weight)
    elif primary_type == "VPN":
        purity = int(100 * totals["vpn"] / total_weight)
    elif primary_type == "Tor":
        purity = int(100 * totals["tor"] / total_weight)
    else:
        purity = 50

    purity = max(0, min(100, purity))
    if source_votes:
        group_votes = [map_kind_to_group(vote) for vote in source_votes if map_kind_to_group(vote) != "unknown"]
        vote_total = len(group_votes)
        if vote_total > 0:
            group_counts = Counter(group_votes)
            top_group_count = group_counts.most_common(1)[0][1]
            second_group_count = group_counts.most_common(2)[1][1] if len(group_counts) > 1 else 0

            agreement_ratio = top_group_count / vote_total
            margin_ratio = (top_group_count - second_group_count) / vote_total if vote_total else 0.0
            coverage_ratio = min(1.0, vote_total / 5.0)

            confidence = int(
                100
                * (
                    agreement_ratio * 0.70
                    + max(0.0, margin_ratio) * 0.20
                    + coverage_ratio * 0.10
                )
            )
        else:
            confidence = 0
    else:
        confidence = 0

    attr_str = f"{', '.join(all_labels)} :: {purity} :: {confidence}"
        
    return full_geo, attr_str

async def fetch_target(
    client: httpx.AsyncClient,
    target: Dict[str, Any],
    ip_analysis_cache: Dict[str, Tuple[str, str]],
) -> Tuple[str, str, str]:
    """Returns (IP/Result, Geolocation, Attribute)"""
    url = target["url"]
    t_type = target.get("type", "text")
    success_statuses = target.get("success_statuses", [])
    
    result_ip = ""
    try:
        response = await client.get(url, timeout=10.0)
        if isinstance(success_statuses, list) and response.status_code in [int(code) for code in success_statuses]:
            success_label = str(target.get("success_label", f"Reachable (HTTP {response.status_code})")).strip()
            return (success_label, "-", "-")
        if response.status_code >= 400:
            return (f"HTTP {response.status_code}", "-", "-")
            
        if t_type == "text":
            result_ip = response.text.strip()
        elif t_type == "json":
            data = response.json()
            if data.get("code", 0) != 0 and data.get("message"):
                return (f"Error: {data.get('message')}", "-", "-")
            
            json_path = target.get("json_path", "")
            if json_path:
                for key in json_path.split("."):
                    if isinstance(data, dict):
                        data = data.get(key, {})
                    else:
                        break
                if isinstance(data, dict) and not data:
                    return ("Path not found", "-", "-")
                result_ip = str(data).strip()
            else:
                result_ip = str(data)
        elif t_type == "cloudflare_trace":
            lines = response.text.split("\n")
            for line in lines:
                if line.startswith("ip="):
                    result_ip = line.split("=", 1)[1].strip()
                    break
            if not result_ip:
                return ("IP not found in trace", "-", "-")
        elif t_type == "header":
            header_name = str(target.get("header_name", "")).strip()
            if not header_name:
                return ("Missing header_name", "-", "-")
            result_ip = response.headers.get(header_name, "").strip()
            if not result_ip:
                return (f"Header not found: {header_name}", "-", "-")
        elif t_type == "body_regex":
            pattern = str(target.get("pattern", "")).strip()
            if not pattern:
                return ("Missing pattern", "-", "-")
            import re
            match = re.search(pattern, response.text, re.S)
            if not match:
                return ("Pattern not found", "-", "-")
            group = int(target.get("group", 1))
            result_ip = match.group(group).strip()
        elif t_type == "status_only":
            result_ip = str(target.get("success_label", f"Reachable (HTTP {response.status_code})")).strip()
        else:
            return (f"Unknown type: {t_type}", "-", "-")
    except httpx.TimeoutException:
        return ("Timeout", "-", "-")
    except httpx.RequestError as e:
        detail = str(e).strip() or e.__class__.__name__
        return (f"Request Error: {detail}", "-", "-")
    except Exception as e:
        return (f"Error: {e}", "-", "-")

    # Now if we successfully got an IP, let's analyze it
    # Basic rudimentary check to ensure it looks like an IP (IPv4 or IPv6)
    if not ":" in result_ip and not "." in result_ip:
        return (result_ip, "-", "-")
        
    cached = ip_analysis_cache.get(result_ip)
    if cached is None:
        cached = await analyze_ip(result_ip)
        ip_analysis_cache[result_ip] = cached

    geo, attr = cached
    return (result_ip, geo, attr)

async def main():
    parser = argparse.ArgumentParser(
        description="AI egress verifier - check whether real target channels look residential or datacenter-like."
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Use 'direct', a real local HTTP/SOCKS proxy port, proxy URL, or a node selector",
    )
    parser.add_argument("-c", "--config", default="targets.toml", help="Path to config file")
    parser.add_argument(
        "-n",
        "--nodes-config",
        default="nodes.toml",
        help="Path to node definitions used for automatic internal bridging",
    )
    parser.add_argument(
        "--show-summary-only",
        action="store_true",
        help="Print the final result table and a short verdict without extra guidance.",
    )
    parser.add_argument(
        "-p",
        "--proxy",
        help="Legacy alias for target: local proxy port, full proxy URL, or 'direct'",
    )
    parser.add_argument(
        "--bridge-command",
        help="Command that starts a bridge/client and exposes a local HTTP/SOCKS proxy",
    )
    parser.add_argument(
        "--bridge-proxy",
        help="Proxy URL exposed by the bridge command, e.g. socks5://127.0.0.1:10808",
    )
    parser.add_argument(
        "--bridge-timeout",
        type=float,
        default=15.0,
        help="Seconds to wait for the bridge proxy to start",
    )
    parser.add_argument(
        "--bridge-cwd",
        default=None,
        help="Working directory for --bridge-command",
    )
    args = parser.parse_args()
    
    config_path = Path(args.config)
    if not config_path.is_file():
        console.print(f"[bold red]Error:[/] Config '{args.config}' not found.")
        sys.exit(1)
        
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        console.print(f"[bold red]Error:[/] TOML parse failed: {e}")
        sys.exit(1)
        
    targets = config.get("targets", [])
    if not targets:
        console.print("[yellow]Warning:[/] No targets found.")

    try:
        nodes = load_nodes_config(Path(args.nodes_config))
    except ConnectorError as e:
        console.print(f"[bold red]Node config error:[/] {e}")
        sys.exit(1)

    relay_endpoints = discover_realm_endpoints()
    singbox_inbounds = discover_singbox_inbounds()

    try:
        connector = build_connector(args, nodes, relay_endpoints, singbox_inbounds)
    except ConnectorError as e:
        console.print(f"[bold red]Connector error:[/] {e}")
        sys.exit(1)

    target_value = args.proxy or args.target or "direct"
    local_inbound_node = None
    if str(target_value).isdigit():
        local_inbound_node = find_local_inbound_node(str(target_value), singbox_inbounds)

    proxies = None
    try:
        proxies = await connector.start()
    except ConnectorError as e:
        console.print(f"[bold red]Connector error:[/] {e}")
        console.print(
            "[yellow]Hint:[/] For non-HTTP/SOCKS protocols, define a matching node in your nodes config. "
            "The script will generate a temporary sing-box config under /tmp, start it internally, "
            "and remove it after the test."
        )
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Startup error:[/] {e}")
        sys.exit(1)

    if local_inbound_node and not find_node(nodes, str(target_value)) and not args.show_summary_only:
        console.print(
            "[yellow]Note:[/] This port looks like a local protocol service. "
            "If it does not route traffic differently from the host itself, "
            "its exit IP may be identical to direct access."
        )

    console.print(f"[bold blue]Testing proxies...[/] Using proxy: {proxies or 'Direct'}")
    
    # Store tuples of (Exit IP, Geolocation, Attribute)
    results = [("Pending...", "-", "-")] * len(targets)
    ip_analysis_cache: Dict[str, Tuple[str, str]] = {}
    
    def generate_table() -> Table:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Target Name", style="cyan")
        table.add_column("Exit IP / Result", justify="left")
        
        for i, target in enumerate(targets):
            res_ip, _, _ = results[i]
            
            color = "green"
            if res_ip.startswith("Pending"):
                color = "yellow"
            elif res_ip.startswith("Error") or "Timeout" in res_ip or res_ip.startswith("HTTP "):
                color = "red"
            elif res_ip.startswith("Request Error"):
                color = "red"

            row = [target.get("name", "Unknown")]
            row.append(f"[{color}]{res_ip}[/]")
            table.add_row(*row)
        return table

    try:
        async with httpx.AsyncClient(proxy=proxies, verify=False, follow_redirects=True, trust_env=False) as client:
            with Live(generate_table(), console=console, refresh_per_second=4) as live:
                tasks = {
                    asyncio.create_task(fetch_target(client, t, ip_analysis_cache)): idx
                    for idx, t in enumerate(targets)
                }

                while tasks:
                    done, pending = await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
                    for done_task in done:
                        idx = tasks.pop(done_task)
                        try:
                            res_tuple = done_task.result()
                        except Exception as e:
                            res_tuple = (f"Error: {e}", "-", "-")
                        results[idx] = res_tuple

                    live.update(generate_table())
    finally:
        await connector.stop()

    summary_ip, unanimous = summarize_exit_ip(results)
    statuses = [classify_residential_status(attr) for ip, _, attr in results if is_ip_like(ip)]
    residential_hits = sum(1 for status in statuses if status == "is 家宽IP")
    non_residential_hits = sum(1 for status in statuses if status == "is not 家宽IP")

    if residential_hits and not non_residential_hits:
        console.print(f"[bold green]Summary:[/] all resolved targets look like residential exits")
    elif non_residential_hits and not residential_hits:
        console.print(f"[bold red]Summary:[/] all resolved targets look non-residential")
    elif residential_hits or non_residential_hits:
        console.print(
            f"[bold yellow]Summary:[/] mixed results: {residential_hits} residential-like, "
            f"{non_residential_hits} non-residential"
        )
    elif summary_ip:
        if unanimous:
            console.print(f"[bold yellow]Summary:[/] all successful targets saw exit IP {summary_ip}, but residential status is unclear")
        else:
            console.print(f"[bold yellow]Summary:[/] most successful targets saw exit IP {summary_ip}, but residential status is unclear")

    rollup = build_ip_rollup(results)
    if rollup:
        rollup_table = Table(show_header=True, header_style="bold cyan")
        rollup_table.add_column("Exit IP")
        rollup_table.add_column("Profile")
        rollup_table.add_column("Score")
        rollup_table.add_column("Confidence")
        rollup_table.add_column("Purity")

        for ip, attr in rollup:
            _, _, confidence = parse_attr(attr)
            rollup_table.add_row(
                ip,
                build_type_label(attr),
                colorize_score_label(attr),
                f"{confidence}%" if confidence is not None else "-",
                build_score_bar(attr),
            )

        console.print()
        console.print("[bold blue]Exit IP Rollup[/]")
        console.print("[dim]Score runs from 0 to 100. Higher is cleaner and lower risk.[/]")
        console.print("[dim]Confidence reflects how consistently multiple IP-intel checks agreed on the high-level residential vs non-residential direction.[/]")
        console.print(rollup_table)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
