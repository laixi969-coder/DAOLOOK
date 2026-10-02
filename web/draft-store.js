/* Unsent business text stays in this tab only, separated by user and project. */
(function (root) {
  'use strict';
  function createDraftStore(storage, now = Date.now) {
    const prefix = 'daolook-draft:';
    const clean = value => {
      const result = {};
      for (const key of ['goal','platform','topic','keyword','requirements','temporary'])
        if (typeof value?.[key] === 'string') result[key] = value[key].slice(0,100000);
      if (Array.isArray(value?.assets)) result.assets = value.assets.filter(x=>typeof x==='string').slice(0,100);
      return result;
    };
    return {
      save(key,value) { try {storage.setItem(prefix+key,JSON.stringify({at:now(),value:clean(value)}));return true;} catch {return false;} },
      read(key) { try { const raw=JSON.parse(storage.getItem(prefix+key));if(!raw || !Number.isFinite(raw.at) || now()-raw.at>86400000 || raw.at>now()) {storage.removeItem(prefix+key);return null;}return clean(raw.value);} catch {return null;} },
      clearUser(user) { try {for(let i=storage.length-1;i>=0;i--){const key=storage.key(i);if(key?.startsWith(prefix+user+':'))storage.removeItem(key);}}catch{} },
    };
  }
  if(typeof module !== 'undefined') module.exports={createDraftStore};
  else root.createDraftStore=createDraftStore;
})(typeof window !== 'undefined' ? window : this);
