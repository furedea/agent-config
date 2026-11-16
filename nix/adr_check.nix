# adr-check: the Python program under tools/adr-check with its PyPI dependencies taken from the pinned inputs.
# The hooks and CI run this command, so neither needs `jsonschema` or a YAML library of its own.
{
  lib,
  stdenvNoCC,
  makeWrapper,
  python,
}:
let
  interpreter = python.withPackages (
    packages: with packages; [
      jsonschema
      ruamel-yaml
    ]
  );
in
stdenvNoCC.mkDerivation {
  pname = "adr-check";
  version = "0.1.0";
  src = ../tools/adr-check;

  nativeBuildInputs = [ makeWrapper ];

  dontBuild = true;
  installPhase = ''
    runHook preInstall

    mkdir -p $out/lib/adr-check $out/bin
    cp -R adrcheck $out/lib/adr-check/
    # -P keeps the working directory off sys.path, so a project cannot shadow the package.
    makeWrapper ${lib.getExe interpreter} $out/bin/adr-check \
      --add-flags "-P -B -m adrcheck" \
      --set PYTHONPATH $out/lib/adr-check

    runHook postInstall
  '';

  meta = {
    description = "Check MADR ADRs against the front-matter shape of ADR-0025";
    mainProgram = "adr-check";
  };
}
