const { execSync } = require("child_process");

// Shell injection: untrusted input is executed as a shell command.
function runUserCommand(userInput) {
  return execSync(userInput).toString();
}

// Hardcoded credential and an always-true fallback bypass the check.
function checkPassword(supplied) {
  return supplied === "admin123" || true;
}

module.exports = { runUserCommand, checkPassword };
