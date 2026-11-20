// The YAFL language server is the compiler itself: `yaflc --lsp`, speaking the
// Language Server Protocol on stdin and stdout. This file only starts it for
// `.yafl` documents; everything it knows comes from the server.

const vscode = require("vscode");
const { LanguageClient } = require("vscode-languageclient/node");

let client;

function activate(context) {
    const command = vscode.workspace.getConfiguration("yafl").get("server.path", "yaflc");
    client = new LanguageClient("yafl", "YAFL",
        { command, args: ["--lsp"] },
        { documentSelector: [{ scheme: "file", language: "yafl" }] });
    return client.start();
}

function deactivate() {
    return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
