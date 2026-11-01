// Run with: node --test tests/test_articles_page.js
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function setup(list) {
    const elements = new Map();
    const document = {
        querySelectorAll: () => [],
        getElementById: id => {
            if (!elements.has(id)) elements.set(id, {style: {}, value: '', innerHTML: '', classList: {toggle() {}}});
            return elements.get(id);
        },
    };
    const context = vm.createContext({document, API: {articles: {list}}, Toast: {}});
    vm.runInContext(fs.readFileSync('frontend/js/components/articles.js', 'utf8') + '\nthis.page = ArticlesPage;', context);
    return {page: context.page, document};
}
test('selecting accounts and switching modes never fetches a list', async () => {
    let calls = 0;
    const {page, document} = setup(() => {calls++;});
    await page.selectAccount('a', 'A');
    page.setSelectionMode('multi');
    await page.selectAccount('b', 'B');
    page.clearSearch();
    assert.equal(calls, 0);
    assert.match(document.getElementById('articles-list').innerHTML, /加载文章列表/);
});
test('explicit loading is single flight and old account response is ignored', async () => {
    let finish, calls = 0;
    const {page} = setup(() => {calls++; return new Promise(resolve => {finish = resolve;});});
    await page.selectAccount('a', 'A');
    const pending = page.loadArticles();
    await page.loadArticles();
    assert.equal(calls, 1);
    await page.selectAccount('b', 'B');
    finish({articles: [{title: 'A article'}], total: 1});
    await pending;
    assert.equal(page.articles.length, 0);
    assert.equal(Object.keys(page.pageCache).length, 0);
});
test('error payload is displayed as failure, not an empty list', async () => {
    const {page, document} = setup(async () => ({error: 'HTTP 429', articles: []}));
    await page.selectAccount('a', 'A');
    await page.loadArticles();
    assert.match(document.getElementById('articles-list').innerHTML, /加载文章列表失败/);
    assert.equal(Object.keys(page.pageCache).length, 0);
});
