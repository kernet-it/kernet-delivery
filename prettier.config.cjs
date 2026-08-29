/** @type {import('prettier').Config} */

// The XML plugin lives in the pre-commit hook environment, whose NODE_PATH
// points at that environment's node_modules. prettier 3 resolves a bare
// plugin name from the working directory, and the repo ships no
// node_modules — so the config resolves the plugin itself, and a machine
// without it simply formats no XML while every other language still runs.
let plugins = [];
try {
    plugins = [require.resolve("@prettier/plugin-xml")];
} catch {
    plugins = [];
}

const config = {
    plugins,
    bracketSpacing: true,
    printWidth: 160,
    proseWrap: "always",
    semi: true,
    trailingComma: "es5",
    arrowParens: "avoid",
    bracketSameLine: true,
    tabWidth: 4,
    xmlQuoteAttributes: "double",
    xmlWhitespaceSensitivity: "strict",
    overrides: [
        {
            // Odoo XML puts a closing bracket on its own line;
            // bracketSameLine stays for the other languages.
            files: "*.xml",
            options: {bracketSameLine: false},
        },
    ],
};

module.exports = config;
