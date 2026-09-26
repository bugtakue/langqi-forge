// Parse generated tests without executing them. Uses the frozen Playwright
// dependency already in the runner, not a package fetched at generation time.
const fs = require('node:fs');
const babel = require('/opt/arcbench/node_modules/playwright/lib/transform/babelBundle.js');
const forbidden = new Set(['constructor', 'prototype', '__proto__', 'eval', 'Function',
  'require', 'process', 'global', 'globalThis', 'module', 'exports', 'fetch',
  'setTimeout', 'setInterval', 'skip', 'fixme', 'only', 'slow', 'soft', 'toPass',
  'use', 'extend', 'configure', 'beforeAll', 'beforeEach', 'afterAll', 'afterEach',
  'route', 'unroute', 'evaluate', 'evaluateAll', 'addInitScript', 'setContent',
  'first', 'last', 'nth', 'getPrototypeOf', 'setPrototypeOf', 'defineProperty',
  'defineProperties', 'getOwnPropertyDescriptor', 'getOwnPropertyDescriptors',
  'call', 'apply', 'bind', 'mainModule', 'createRequire']);
const globals = new Set(['Date', 'Math', 'JSON', 'String', 'Number', 'Boolean',
  'Array', 'Object', 'RegExp', 'Error', 'URL', 'undefined', 'NaN', 'Infinity']);
// Closed surface: generated code cannot use arbitrary Browser/Node methods.
// This supplements, not replaces, the separate no-network grading container.
const members = new Set(['goto', 'reload', 'goBack', 'url', 'getByRole', 'getByLabel',
  'getByText', 'getByPlaceholder', 'getByTestId', 'locator', 'filter', 'and', 'or',
  'click', 'dblclick', 'fill', 'press', 'check', 'uncheck', 'selectOption',
  'inputValue', 'textContent', 'innerText', 'count', 'getAttribute', 'isVisible',
  'newContext', 'newPage', 'close', 'context', 'waitForURL',
  'toHaveText', 'toContainText', 'toBeVisible', 'toBeHidden', 'toHaveValue',
  'toHaveAttribute', 'toHaveURL', 'toHaveCount', 'toBeChecked', 'toBeEnabled',
  'toBeDisabled', 'toEqual', 'toBe', 'toContain', 'toMatch', 'toBeTruthy', 'toBeFalsy', 'not',
  'now', 'random', 'floor', 'ceil', 'min', 'max', 'abs', 'round',
  'toString', 'slice', 'substring', 'replace', 'replaceAll', 'trim',
  'toLowerCase', 'toUpperCase', 'startsWith', 'endsWith', 'includes',
  'split', 'join', 'length', 'map', 'forEach', 'push', 'stringify', 'parse',
  'keys', 'values', 'entries', 'pathname', 'href', 'origin', 'filename', 'text']);

function reject(message) { throw new Error(message); }
function member(path) {
  const n = path.node;
  if (n.computed) reject('computed property lookup is not allowed');
  if (forbidden.has(n.property.name)) reject('forbidden member: ' + n.property.name);
  if (!members.has(n.property.name)) reject('member outside UI test surface: ' + n.property.name);
  if (n.object.type === 'Identifier' && n.object.name === 'request')
    reject('business API requests are not allowed; use UI or restart(request)');
}
function validate(source) {
  const ast = babel.babelParse(source, 'contract.spec.ts', true);
  for (const statement of ast.program.body) {
    if (statement.type === 'ImportDeclaration' || statement.type === 'FunctionDeclaration') continue;
    const call = statement.type === 'ExpressionStatement' && statement.expression;
    if (!call || call.type !== 'CallExpression' || call.callee.name !== 'test')
      reject('helpers may contain function declarations only; no top-level side effects');
  }
  babel.traverse(ast, {
    ImportDeclaration(path) {
      if (!['@playwright/test', './restart', './io'].includes(path.node.source.value))
        reject('unapproved import');
    },
    ReferencedIdentifier(path) {
      const name = path.node.name;
      if (forbidden.has(name)) reject('forbidden identifier: ' + name);
      if (!path.scope.hasBinding(name, true) && !globals.has(name))
        reject('unbound global: ' + name);
    },
    BindingIdentifier(path) {
      if (['test','expect','restart','uploadCsv','downloadCsv'].includes(path.node.name) && !path.parentPath.isImportSpecifier())
        reject('cannot rebind acceptance primitives');
    },
    MemberExpression: member,
    OptionalMemberExpression: member,
    ObjectProperty(path) {
      if (path.node.computed || forbidden.has(path.node.key.name || path.node.key.value))
        reject('forbidden object property');
    },
    TryStatement() { reject('test failures must not be caught'); },
    WhileStatement() { reject('unbounded loops are not allowed'); },
    DoWhileStatement() { reject('unbounded loops are not allowed'); },
    Import() { reject('dynamic imports are not allowed'); },
    CallExpression(path) {
      const n=path.node;
      if (n.callee.type==='Identifier' && n.callee.name==='test' && !path.parentPath.parentPath.isProgram())
        reject('nested test registration is not allowed');
      if (n.callee.type==='Identifier' && n.callee.name==='expect' &&
          (!n.arguments[0] || /Literal$/.test(n.arguments[0].type)))
        reject('constant assertions are not behavior acceptance');
      if (n.callee.type === 'MemberExpression' && /^to[A-Z]/.test(n.callee.property.name)) {
        for (const argument of path.get('arguments')) {
          if (argument.isAwaitExpression()) reject('expected values must not be read from the current UI');
          argument.traverse({AwaitExpression() {reject('expected values must not be read from the current UI');}});
        }
      }
    }
  });
  return true;
}
try {
  const input=JSON.parse(fs.readFileSync(0,'utf8'));
  validate(input.source);
  console.log(JSON.stringify({valid:true}));
} catch (error) {
  console.log(JSON.stringify({valid:false,error:String(error.message)}));
  process.exitCode=1;
}
