// 清空 IndexedDB（删除该域名下所有数据库）
async () => {
    try {
        const dbs = await indexedDB.databases();
        for (const db of dbs) {
            indexedDB.deleteDatabase(db.name);
        }
    } catch (e) {}
}
