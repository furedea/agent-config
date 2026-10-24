# agent-config

<p align="center">
  <a href="README.md"><img alt="English" src="https://img.shields.io/badge/lang-English-8c959f"></a>
  <a href="README_ja.md"><img alt="日本語" src="https://img.shields.io/badge/lang-%E6%97%A5%E6%9C%AC%E8%AA%9E-0969da"></a>
</p>

[agent-harness](https://github.com/furedea/agent-harness) の個人用ソース．プロバイダ中立の指示，スキル，フック，権限ルールを持ち，それらが `~/.claude` と `~/.codex` にレンダリングされる．

## レイアウト

| パス                          | 内容                                                            |
| ----------------------------- | --------------------------------------------------------------- |
| `agents/`                     | harness のソース（ソースレイアウトのバージョン 1）              |
| `tests/`                      | ソースに対する pytest と Bats の仕様                            |
| `scripts/bootstrap_server.sh` | Nix のないサーバーに harness をインストールする                 |
| `docs/DESIGN.md`              | 開発サイクル，検証，フックの判断                                |
| `docs/adr/`                   | ソースに関する判断                                              |
| `CONTRIBUTING.md`             | ローカルの変更を確認する方法                                    |
| `flake.nix`                   | `packages.default`: シバンを Python 3.15.1 に固定した `agents/` |

## 使い方

Nix では，`inputs.agent-config.packages.${system}.default` を agent-harness の Home Manager モジュールの `source` として読み込む．Nix を使わない場合は，このリポジトリをクローンして `scripts/bootstrap_server.sh` を実行する．

## Nix なしで Linux サーバーにブートストラップする

Nix も root 権限もない x86_64 の Linux サーバーでは，このリポジトリをクローンしてブートストラップを実行する：

```sh
mkdir -p "$HOME/ghq/github.com/furedea"
git clone https://github.com/furedea/agent-config \
  "$HOME/ghq/github.com/furedea/agent-config"
cd "$HOME/ghq/github.com/furedea/agent-config"
bash scripts/bootstrap_server.sh
. "$HOME/.config/agent-config/agent_env.sh"
```

このスクリプトは，バージョンを固定した x86_64 Linux 向けのリリースバイナリ（`agent-harness`，`shfmt`，`rg`，`jq`，`ruff`，`dprint`，`shellcheck`，`bats`，`uv`）を `~/.local/bin` にダウンロードし，uv で Python 3.15.1 をインストールし，同じ `agent-harness` CLI で `agents/` をホームディレクトリにレンダリングし，フックのシバンをそのインタプリタに固定し，Claude Code が実行時に書き込んだ設定を保持し，ログインシェルが読み込む `~/.config/agent-config/agent_env.sh` を書き出す．他のアーキテクチャでは何もインストールする前に終了する．ソースからビルドする手順はスクリプトを参照．

最後のコマンドは現在のシェルの `PATH` を更新する．今後のシェルでもツールを使えるように，同じ行を `~/.profile` か `~/.bashrc` に追加する．既存のサーバーを更新するには，次を実行する：

```sh
cd "$HOME/ghq/github.com/furedea/agent-config"
git pull --ff-only
bash scripts/bootstrap_server.sh
```

ホスト固有の設定はリポジトリの外の `~/.config/agent-config/` に置く．`bootstrap_server.env` は `BIN_DIR`，`UV_PYTHON_INSTALL_DIR`，`UV_CACHE_DIR`，`XDG_CACHE_HOME` などの場所を設定し（`--help` を参照），`claude_settings_override.json` はレンダリングされた Claude Code の設定にマージされる．フックの状態は `~/.local/state` に残る．ソースが独自のリポジトリを持つ理由は [ADR-0012](docs/adr/0012_keep_the_personal_agent_source_in_its_own_repository.md) を参照．

## 検証とフック

フックは各セッションの worktree を登録し，変更を自動的に検証する．状態，有効期限，300 秒のチェック時間の上限，allow，ask，deny のポリシーは [`docs/DESIGN.md`](docs/DESIGN_ja.md) に記述している．そこにある開発サイクルが，作業がマージ済みのプルリクエストに至る流れである．

## 開発

```sh
nix develop
uv run pytest
bats tests/bootstrap_server.bats
```

レンダリングされた出力で変更を確認する前に，[`CONTRIBUTING.md`](CONTRIBUTING.md) を参照．

インポートまでの履歴は `furedea/dotfiles` に由来する．それらのコミットメッセージにある `#NNN` は，そのリポジトリの Issue とプルリクエストを指す．
