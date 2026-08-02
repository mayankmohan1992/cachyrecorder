.RECIPEPREFIX := >
.PHONY: check lint deploy verify all

# Canonical entry point: static checks + live runtime gate.
check: lint verify

lint:
> uvx ruff check src/cachyrec
> bash -n scripts/deploy.sh scripts/verify.sh scripts/cachyrec-launcher.sh
> python3 -m compileall -q src/cachyrec

deploy:
> ./scripts/deploy.sh

# Requires a live KDE Plasma Wayland session.
verify:
> ./scripts/verify.sh

all: lint deploy verify
