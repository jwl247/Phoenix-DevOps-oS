'use strict';
// helix_packet.js — JS QuadralingualPacket / Helix memory (SectorID.CLAUDE)
// Mirrors coms1/freewheeling.py packet format. NOSQL computed hot; rest lazy.
// Phoenix DevOps OS / jwl247 / GPL v3

class HelixPacket {
    constructor(id, raw) {
        this.packet_id  = id;
        this.created_at = Date.now() / 1000;
        this._raw       = raw;
        this._nosql     = this._mkNosql();   // hot — needed immediately
        this._vector    = null;              // lazy
        this._relational= null;              // lazy
        this._timeseries= null;              // lazy
    }

    _mkNosql() {
        const t = Array.isArray(this._raw) ? 'list' : typeof this._raw;
        const base = { _id: this.packet_id, _created: this.created_at, _type: t };
        if (this._raw && typeof this._raw === 'object' && !Array.isArray(this._raw))
            base.data = this._raw;
        else if (typeof this._raw === 'string')
            base.data = { text: this._raw, length: this._raw.length };
        else if (Array.isArray(this._raw))
            base.data = { items: this._raw, length: this._raw.length };
        else
            base.data = { value: this._raw };
        return base;
    }

    _mkVector() {
        const r = this._raw;
        if (Array.isArray(r) && r.every(x => typeof x === 'number')) return r.map(Number);
        if (r && typeof r === 'object' && !Array.isArray(r))
            return Object.keys(r).sort().flatMap(k => {
                const v = r[k];
                return typeof v === 'number' ? [v]
                     : typeof v === 'string' ? [(v.split('').reduce((a,c)=>a+c.charCodeAt(0),0)%1000)/1000]
                     : [];
            });
        if (typeof r === 'string') return [...r.slice(0,128)].map(c=>c.charCodeAt(0)/255);
        if (typeof r === 'number') return [r];
        return [(String(r).split('').reduce((a,c)=>a+c.charCodeAt(0),0)%1000)/1000];
    }

    _mkRelational() {
        const row = { id: this.packet_id, created_at: this.created_at, data_type: typeof this._raw };
        if (this._raw && typeof this._raw === 'object' && !Array.isArray(this._raw))
            for (const [k,v] of Object.entries(this._raw))
                row[`col_${k.replace(/\s+/g,'_').toLowerCase()}`] =
                    ['number','string','boolean'].includes(typeof v) ? v : String(v);
        else if (typeof this._raw === 'string')
            Object.assign(row, { text_value: this._raw, text_length: this._raw.length });
        const vec = this.asVector();
        if (vec.length) row.vector_magnitude = Math.sqrt(vec.reduce((s,x)=>s+x*x,0));
        return row;
    }

    _mkTimeseries() {
        const r = this._raw, t = this.created_at;
        if (r && typeof r === 'object' && !Array.isArray(r))
            return Object.entries(r).map(([k,v],i)=>({ timestamp:t+i*.001, metric:k, value:typeof v==='number'?v:null, value_str:typeof v!=='number'?String(v):null, sequence:i }));
        if (Array.isArray(r))
            return r.map((x,i)=>({ timestamp:t+i*.001, metric:`item_${i}`, value:typeof x==='number'?x:null, value_str:typeof x!=='number'?String(x):null, sequence:i }));
        return [{ timestamp:t, metric:'value', value:typeof r==='number'?r:null, value_str:String(r), sequence:0 }];
    }

    asNosql()      { return this._nosql; }
    asVector()     { return this._vector     ?? (this._vector     = this._mkVector()); }
    asRelational() { return this._relational ?? (this._relational = this._mkRelational()); }
    asTimeseries() { return this._timeseries ?? (this._timeseries = this._mkTimeseries()); }
    raw()          { return this._raw; }
    toBytes()      { return Buffer.from(JSON.stringify(this._nosql)); }

    static fromData(id, data)  { return new HelixPacket(id, data); }
    static fromBytes(buf)      { const n = JSON.parse(buf); return new HelixPacket(n._id, n.data ?? n); }
}

class HelixMemoryJS {
    constructor(maxTurns = 40) {
        this._turns     = [];
        this._index     = new Map();
        this._max       = maxTurns;
        this._seq       = 0;
        this.sessionId  = `js_${Date.now()}`;
    }

    pushTurn(role, content) {
        const id  = `cl:${this.sessionId}:${++this._seq}`;
        const pkt = HelixPacket.fromData(id, { role, content, seq: this._seq });
        this._turns.push(pkt);
        this._index.set(id, pkt);
        if (this._turns.length > this._max) this._index.delete(this._turns.shift().packet_id);
        return pkt;
    }

    getHistory(max = 20)  { return (max ? this._turns.slice(-max) : this._turns).map(p => ({ role: p.raw().role, content: p.raw().content })); }
    getAllNosql()          { return this._turns.map(p => p.asNosql()); }
    getAllVectors()        { return this._turns.map(p => ({ id: p.packet_id, vec: p.asVector() })); }
    get seq()             { return this._seq; }
    clear()               { this._turns = []; this._index.clear(); this._seq = 0; }
}

module.exports = { HelixPacket, HelixMemoryJS };
