# Publishing to GitHub and HACS

## One-time GitHub setup

1. Create a new **empty public** repository on GitHub — no README, no .gitignore.
   Suggested name: `heatmiser_schedule_manager`

2. From a terminal on your HA host, initialise the repo and push:

```sh
cd /config/heatmiser_schedule_manager
git init
git add -A
git commit -m "Initial release"
./git-manager.sh setup
```

`setup` will prompt for:
- GitHub username
- GitHub email
- Repo path (e.g. `youruser/heatmiser_schedule_manager`)
- Personal Access Token (create one at https://github.com/settings/tokens/new — scope: **repo**)

3. Push to GitHub:

```sh
git push -u origin main
```

4. Create the first release (the version must match `manifest.json` — currently `1.0.0`):

```sh
./git-manager.sh release v1.0.0 "Version 1.0.0" "Initial release"
```

HACS requires at least one tagged release before the integration can be installed.

---

## Ongoing workflow

After making changes to integration files, sync them from the working copy into this repo directory, then push:

```sh
# Copy updated files from the live integration
cp /config/custom_components/heatmiser_schedule_manager/__init__.py \
   /config/heatmiser_schedule_manager/custom_components/heatmiser_schedule_manager/

# Commit and push
cd /config/heatmiser_schedule_manager
./git-manager.sh push "Describe what changed"
```

To publish a new version:

1. Update the `version` field in `custom_components/heatmiser_schedule_manager/manifest.json`
2. Copy all changed files into this repo directory
3. Commit, push, and release:

```sh
./git-manager.sh push "Bump version to 1.1.0"
./git-manager.sh release v1.1.0 "Version 1.1.0" "Brief description of changes"
```

---

## Installing via HACS (custom repository)

Before submitting to the HACS default list, install and test via a custom repository:

1. In HA, go to **HACS → Integrations → ⋮ → Custom repositories**
2. Add your GitHub repo URL (e.g. `https://github.com/youruser/heatmiser_schedule_manager`)
3. Set category to **Integration**
4. Click **Add**
5. Search for **Heatmiser Schedule Manager** in HACS and install
6. Restart Home Assistant

---

## Submitting to the HACS default list (optional)

Once the integration is tested and stable:

1. Ensure your repo meets the [HACS requirements](https://hacs.xyz/docs/publish/start)
   - Public GitHub repo
   - `hacs.json` at root ✓
   - `custom_components/<domain>/manifest.json` with `version` ✓
   - At least one GitHub release ✓
   - README at repo root ✓
2. Submit a PR to [hacs/default](https://github.com/hacs/default) adding your repo to `integration` category

---

## Useful git-manager.sh commands

| Command | Description |
|---------|-------------|
| `./git-manager.sh setup` | Configure git user, token, and remote |
| `./git-manager.sh status` | Show current git status |
| `./git-manager.sh push "message"` | Stage all, commit, and push |
| `./git-manager.sh log` | Show last 10 commits |
| `./git-manager.sh tag v1.2.0` | Create and push an annotated tag |
| `./git-manager.sh release v1.2.0 "Title" "Notes"` | Create a GitHub release |
| `./git-manager.sh list-releases` | List all GitHub releases |
