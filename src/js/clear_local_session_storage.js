// 清空 LocalStorage 和 SessionStorage
() => {
    try { localStorage.clear(); } catch (e) {}
    try { sessionStorage.clear(); } catch (e) {}
}
