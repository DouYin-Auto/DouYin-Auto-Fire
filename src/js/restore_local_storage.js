// 恢复 LocalStorage 数据
(data) => {
    for (const [key, value] of Object.entries(data)) {
        localStorage.setItem(key, value);
    }
}
