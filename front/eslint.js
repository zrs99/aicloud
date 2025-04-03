module.exports = {
  root: true,

  env: {
    node: true,
    'vue/setup-compiler-macros': true, // 支持Vue3的编译宏
  },

  extends: [
    'plugin:vue/vue3-essential',  // Vue 3 相关的 ESLint 规则
    '@vue/airbnb',                // 使用 Airbnb 的 JavaScript 风格指南
    '@vue/typescript/recommended', // TypeScript 支持（如果你使用 TS）
  ],

  parserOptions: {
    ecmaVersion: 2020,  // 支持现代 ECMAScript 特性
  },

  rules: {
    'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off', // 生产环境下警告 console
    'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off', // 生产环境下警告 debugger
  },
};
