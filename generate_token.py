#!/usr/bin/env python3
"""Gera o token.json de usuário autorizado usado pelo upload ao Google Drive.

O fluxo OAuth é interativo e abre um navegador. Rode uma vez; o
``gdrive_uploader`` passa a encontrar a credencial sozinho pelo mesmo caminho.

    python3 generate_token.py <client_secrets.json> [-o <destino>]

O destino padrão é o mesmo que o uploader lê (``GOOGLE_TOKEN_FILE`` ou
``DEFAULT_TOKEN_PATH``). Nenhum segredo é impresso: o arquivo gravado é a única
saída sensível e nasce com permissão 0600.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from youtube_clipper.gdrive_uploader import DEFAULT_TOKEN_PATH, SCOPES

_HOW_TO_GET_SECRETS = """
Para obter o arquivo client_secrets.json:
1. Acesse o Google Cloud Console (https://console.cloud.google.com/)
2. Crie ou selecione um projeto e habilite a 'Google Drive API'
3. Vá em 'Credenciais' -> 'Criar Credenciais' -> 'ID do cliente OAuth'
4. Selecione o tipo de aplicativo 'App de desktop'
5. Baixe o arquivo JSON das credenciais e passe o caminho para este script.
""".strip()


def resolve_token_path(explicit: str | None) -> Path:
    """Resolve o destino do token na mesma ordem de precedência do uploader."""
    chosen = explicit or os.environ.get("GOOGLE_TOKEN_FILE") or DEFAULT_TOKEN_PATH
    return Path(chosen).expanduser()


def write_token(token_path: Path, payload: str) -> None:
    """Grava o token com permissão restrita antes de qualquer conteúdo entrar nele."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    # Abrir com O_CREAT|O_EXCL-like semantics não serve aqui porque regerar o
    # token é legítimo; em vez disso o modo restrito é aplicado na criação e
    # reforçado depois, para o caso de o arquivo já existir com 0644.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
    finally:
        os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera o token.json de usuário autorizado para o Google Drive.",
        epilog=_HOW_TO_GET_SECRETS,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "client_secrets",
        help="caminho para o client_secrets.json baixado do Google Cloud Console",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "destino do token.json "
            "(padrão: $GOOGLE_TOKEN_FILE ou o caminho lido pelo uploader)"
        ),
    )
    args = parser.parse_args()

    client_secrets_path = Path(args.client_secrets).expanduser()
    if not client_secrets_path.exists():
        print(f"Erro: O arquivo '{client_secrets_path}' não foi encontrado.", file=sys.stderr)
        print(f"\n{_HOW_TO_GET_SECRETS}", file=sys.stderr)
        return 1

    token_path = resolve_token_path(args.output)

    print("Iniciando fluxo de autenticação OAuth2...")
    print(f"Escopos solicitados: {', '.join(SCOPES)}")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), SCOPES)
        creds = flow.run_local_server(port=0)
    except Exception as exc:
        print(f"\n❌ Erro durante a autenticação: {exc}", file=sys.stderr)
        return 1

    if not creds.refresh_token:
        print(
            "\n❌ O Google não devolveu refresh_token. Isso acontece quando a conta "
            "já autorizou este client antes. Revogue o acesso em "
            "https://myaccount.google.com/permissions e rode de novo.",
            file=sys.stderr,
        )
        return 1

    try:
        write_token(token_path, creds.to_json())
    except OSError as exc:
        print(f"\n❌ Falha ao gravar o token em {token_path}: {exc}", file=sys.stderr)
        return 1

    print(f"\n✅ Token gravado (modo 0600) em:\n   {token_path}")
    if not args.output and not os.environ.get("GOOGLE_TOKEN_FILE"):
        print("\nO uploader já lê esse caminho por padrão — nada mais a configurar.")
    else:
        print(
            "\nExporte o caminho para o uploader encontrá-lo:\n"
            f'   export GOOGLE_TOKEN_FILE="{token_path}"'
        )
    print(
        "\nAlternativa sem arquivo: o uploader também aceita GOOGLE_CLIENT_ID, "
        "GOOGLE_CLIENT_SECRET e GOOGLE_REFRESH_TOKEN no ambiente. Os valores "
        "estão no client_secrets.json e no token recém-gravado; este script não "
        "os imprime para não deixar segredo no histórico do terminal."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
