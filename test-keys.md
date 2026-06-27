Charon Install:

In your own WSL terminal (not the ! here — charon setup prompts for keys and needs a real terminal):

1. Install it once (it's not on PATH yet):
cd /home/stack/code/charon
pipx install .            # isolated, recommended  — or:  pip install -e .

2. Configure once (adds providers + keys → stored in ~/.charon):
charon setup              # guided, or:  charon providers add openrouter

3. Start the gateway:
charon gateway
→ serves http://127.0.0.1:8080/v1, console at http://127.0.0.1:8080/. It runs in the foreground (serves until Ctrl-C) — leave it running and open another terminal for your client.

4. Point your client (OpenCode, Cursor, …) at http://127.0.0.1:8080/v1.

Don't want to install? Run it straight from the repo:
cd /home/stack/code/charon
PYTHONPATH=src python3 -m charon.cli gateway

Ubuntu / Debian:
sudo apt update && sudo apt install -y pipx git
pipx ensurepath && exec $SHELL          # puts ~/.local/bin on PATH
pipx install git+https://github.com/SLOP-Platform/charon
charon setup        # add providers + keys
charon gateway      # serves http://127.0.0.1:8080/v1

Alternative — uv (no apt, works on any distro):
curl -LsSf https://astral.sh/uv/install.sh | sh        # installs uv
uv tool install git+https://github.com/SLOP-Platform/charon
charon setup ; charon gateway
