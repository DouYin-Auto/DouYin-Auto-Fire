// 导出当前页面的 LocalStorage
() => {
    const result = {};
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        result[key] = localStorage.getItem(key);
    }
    return result;
}
