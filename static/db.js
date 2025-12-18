
const DB_NAME = "DecaAppDB";
const DB_VERSION = 1;
const STORE_TESTS = "tests";

const dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains(STORE_TESTS)) {
            db.createObjectStore(STORE_TESTS, { keyPath: "id" });
        }
    };

    request.onsuccess = (event) => {
        resolve(event.target.result);
    };

    request.onerror = (event) => {
        console.error("IndexedDB error:", event.target.error);
        reject(event.target.error);
    };
});

const IDB = {
    async getAllTests() {
        const db = await dbPromise;
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_TESTS], "readonly");
            const store = transaction.objectStore(STORE_TESTS);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    },

    async saveTest(test) {
        if (!test || !test.id) return;
        const db = await dbPromise;
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_TESTS], "readwrite");
            const store = transaction.objectStore(STORE_TESTS);
            const request = store.put(test);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    },

    async getTest(id) {
        const db = await dbPromise;
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_TESTS], "readonly");
            const store = transaction.objectStore(STORE_TESTS);
            const request = store.get(id);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    },

    async deleteTest(id) {
        const db = await dbPromise;
        return new Promise((resolve, reject) => {
            const transaction = db.transaction([STORE_TESTS], "readwrite");
            const store = transaction.objectStore(STORE_TESTS);
            const request = store.delete(id);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }
};
