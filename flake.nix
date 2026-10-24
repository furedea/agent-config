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
      pythonFor = pkgs: pkgs.callPackage ./nix/python.nix { };
      uvFor = pkgs: pkgs.callPackage ./nix/uv.nix { };
    in
    {
      # Environment variables every agent host exports; scripts/bootstrap_server.sh reads the same file.
      lib.agentEnvironment = builtins.fromJSON (builtins.readFile ./agent_environment.json);

      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          # The rendered hooks run on this interpreter, so shebangs are pinned at build time.
          default = pkgs.runCommand "agent-source" { buildInputs = [ (pythonFor pkgs) ]; } ''
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
          # An executable keeping `env python3` would run an unpinned interpreter.
          pinned-shebangs =
            pkgs.runCommand "agent-source-pinned-shebangs" { nativeBuildInputs = [ pkgs.findutils ]; }
              ''
                status=0
                while IFS= read -r -d "" file; do
                  if head -n 1 "$file" | grep -Eq '^#!/usr/bin/env (-S )?python'; then
                    echo "unpinned Python shebang: $file" >&2
                    status=1
                  fi
                done < <(find ${source} -type f -perm -u+x -print0)
                [ "$status" -eq 0 ]
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
                ripgrep
                shellcheck
                shfmt
                statix
              ])
              ++ [
                (pythonFor pkgs)
                (uvFor pkgs)
              ]
              # agent-harness publishes its package for macOS only; CI installs the locked revision itself.
              ++ nixpkgs.lib.optional (
                agent-harness.packages ? ${system}
              ) agent-harness.packages.${system}.default
              ++ [
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
