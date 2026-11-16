# adr-check: the Python application under tools/adr-check, built from its own pyproject.toml.
# The hooks and CI run this command, so neither needs `jsonschema` or a YAML library of its own.
{ python3Packages }:
let
  inherit (builtins.fromTOML (builtins.readFile ../tools/adr-check/pyproject.toml)) project;
in
python3Packages.buildPythonApplication {
  pname = project.name;
  inherit (project) version;
  pyproject = true;
  src = ../tools/adr-check;

  build-system = [ python3Packages.hatchling ];
  dependencies = with python3Packages; [
    jsonschema
    ruamel-yaml
  ];

  pythonImportsCheck = [ "adrcheck" ];

  meta = {
    inherit (project) description;
    mainProgram = "adr-check";
  };
}
