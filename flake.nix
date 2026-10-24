{
  description = "Personal agent-harness source, rendered by agent-harness";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    agent-harness = {
      url = "github:furedea/agent-harness";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.nixpkgs-unstable.follows = "nixpkgs-unstable";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      nixpkgs-unstable,
      agent-harness,
      ...
    }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: import nixpkgs { inherit system; };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          # The rendered hooks run on this interpreter, so shebangs are pinned at build time.
          default = pkgs.runCommand "agent-source" { buildInputs = [ pkgs.python314 ]; } ''
            cp -R ${./agents}/. "$out"
            chmod -R u+w "$out"
            patchShebangs --host "$out"
          '';
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          source = self.packages.${system}.default;
        in
        {
          # Nix store paths only: a leftover `env python3` shebang would run an unpinned interpreter.
          pinned-shebangs =
            pkgs.runCommand "agent-source-pinned-shebangs" { nativeBuildInputs = [ pkgs.ripgrep ]; }
              ''
                if rg -l --no-messages '^#!/usr/bin/env (-S )?python' ${source}; then
                  echo "agent source still has unpinned Python shebangs" >&2
                  exit 1
                fi
                touch "$out"
              '';

          bootstrap-server =
            pkgs.runCommand "bootstrap-server-bats"
              {
                nativeBuildInputs = with pkgs; [
                  bash
                  bats
                  coreutils
                  gnutar
                  jq
                  xz
                ];
              }
              ''
                cp -R ${./.}/. work
                chmod -R u+w work
                cd work
                bats tests/bootstrap_server.bats
                touch "$out"
              '';
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            packages =
              (with pkgs; [
                bats
                commitlint
                deadnix
                jq
                ls-lint
                nixfmt
                python314
                ripgrep
                shellcheck
                shfmt
                statix
                uv
              ])
              ++ [
                agent-harness.packages.${system}.default
                # lefthook before 2.1.6 runs hooks under a pty, which agent sandboxes deny.
                nixpkgs-unstable.legacyPackages.${system}.lefthook
              ];

            env = {
              UV_PYTHON_DOWNLOADS = "never";
              UV_PYTHON_PREFERENCE = "only-system";
            };

            shellHook = ''
              if [ -d .venv/bin ]; then
                export PATH="$PWD/.venv/bin:$PATH"
              fi
            '';
          };
        }
      );
    };
}
