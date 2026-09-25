// Static lexical analysis only: never import/evaluate generated application code
// or discover its configuration. This is deliberately not a general lint suite.
import { parse, latestEcmaVersion } from 'espree';
import { analyze } from 'eslint-scope';
import { KEYS } from 'eslint-visitor-keys';
import globals from 'globals';

function typeofIdentifiers(ast) {
  const exempt = new Set();
  const pending = [ast];
  while (pending.length) {
    const node = pending.pop();
    if (node.type === 'UnaryExpression' && node.operator === 'typeof'
        && node.argument.type === 'Identifier') exempt.add(node.argument);
    for (const key of KEYS[node.type] || []) {
      const child = node[key];
      if (Array.isArray(child)) pending.push(...child.filter(Boolean));
      else if (child) pending.push(child);
    }
  }
  return exempt;
}

function inspect(file) {
  const commonjs = file.sourceType === 'commonjs';
  const sourceType = commonjs ? 'script' : file.sourceType;
  const options = {
    ecmaVersion: latestEcmaVersion, sourceType, range: true, loc: true,
    ecmaFeatures: {globalReturn: commonjs},
  };
  const ast = parse(file.source, options);
  const scopes = analyze(ast, {
    ecmaVersion: latestEcmaVersion, sourceType, nodejsScope: commonjs,
    ignoreEval: true, childVisitorKeys: KEYS,
  });
  const known = new Set(Object.keys({
    ...globals.es2025,
    ...(commonjs ? globals.commonjs : {}),
    ...(file.environment === 'browser' ? globals.browser
      : (commonjs ? globals.node : globals.nodeBuiltin)),
  }));
  for (const variable of scopes.globalScope.variables) known.add(variable.name);
  const exempt = typeofIdentifiers(ast);
  const messages = [];
  for (const reference of scopes.globalScope.through) {
    const identifier = reference.identifier;
    if (known.has(identifier.name) || exempt.has(identifier)) continue;
    messages.push({
      line: identifier.loc.start.line, column: identifier.loc.start.column + 1,
      message: `Undeclared variable: ${identifier.name.slice(0, 100)}`,
    });
    if (messages.length === 10) break;
  }
  return {path: file.path, messages};
}

async function main() {
  let bytes = 0;
  const chunks = [];
  for await (const chunk of process.stdin) {
    bytes += chunk.length;
    if (bytes > 10 * 1024 * 1024) throw new Error('input limit exceeded');
    chunks.push(chunk);
  }
  const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if (!Array.isArray(input.files) || input.files.length > 120) {
    throw new Error('invalid file list');
  }
  const results = [];
  for (const file of input.files) {
    if (typeof file.path !== 'string' || file.path.length > 1024
        || typeof file.source !== 'string'
        || Buffer.byteLength(file.source) > 2_000_000
        || !['browser', 'node'].includes(file.environment)
        || !['module', 'commonjs', 'script'].includes(file.sourceType)) {
      throw new Error('invalid source record');
    }
    try { results.push(inspect(file)); }
    catch (error) {
      results.push({path: file.path, messages: [{
        line: error.lineNumber || 0, column: error.column || 0,
        message: `Cannot analyze source: ${String(error.message).slice(0, 200)}`,
      }]});
    }
  }
  process.stdout.write(JSON.stringify({results}));
}
main().catch(() => {
  process.stderr.write('JavaScript scope checker: invalid or excessive input\n');
  process.exitCode = 1;
});
