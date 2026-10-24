{
  fetchurl,
  lib,
  stdenvNoCC,
  versionCheckHook,
}:

let
  version = "0.13.5";
  # Static builds on Linux, so the binary needs no patching for the Nix store.
  targets = {
    aarch64-darwin = {
      triple = "aarch64-apple-darwin";
      hash = "sha256-dD+FA1oZluyzUGWeAc2frqlwmCm+CbG0sDxz6vPJzXM=";
    };
    x86_64-darwin = {
      triple = "x86_64-apple-darwin";
      hash = "sha256-sPUrDjlFtBB9iQJOo45iVoMBH7/AWg2Y+fotbc7ijGY=";
    };
    aarch64-linux = {
      triple = "aarch64-unknown-linux-musl";
      hash = "sha256-eQbHmtshyBq9VZhBuna7HZr515GsrHoEGyly4DrhZTg=";
    };
    x86_64-linux = {
      triple = "x86_64-unknown-linux-musl";
      hash = "sha256-V++dnMsB+xvZmN+ZWw3SIbUvfXhB++qT8tRGO/Yft6k=";
    };
  };
  target = targets.${stdenvNoCC.hostPlatform.system};
in
# TODO: Return to pkgs.uv once the nixpkgs input ships uv 0.13.5 or later; the nixpkgs
# input still ships 0.11.x or 0.13.0, which predate the managed CPython 3.14.9 and 3.15.1.
stdenvNoCC.mkDerivation {
  pname = "uv";
  inherit version;

  src = fetchurl {
    url = "https://github.com/astral-sh/uv/releases/download/${version}/uv-${target.triple}.tar.gz";
    inherit (target) hash;
  };

  dontBuild = true;
  dontStrip = true;

  installPhase = ''
    runHook preInstall
    install -Dm755 -t "$out/bin" uv uvx
    runHook postInstall
  '';

  nativeInstallCheckInputs = [ versionCheckHook ];
  doInstallCheck = true;

  meta = {
    description = "Python package and project manager, official build";
    homepage = "https://github.com/astral-sh/uv";
    license = with lib.licenses; [
      asl20
      mit
    ];
    mainProgram = "uv";
    platforms = builtins.attrNames targets;
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
  };
}
