import vm from 'vm';

const LUNR_SCRIPT = 'https://cdnjs.cloudflare.com/ajax/libs/lunr.js/2.3.9/lunr.min.js',
    stdin = process.stdin,
    stdout = process.stdout,
    buffer = [];

async function loadScript(url) {
    const response = await fetch(url);
    return await response.text();
}
async function executeScript(script) {
    const sandbox = { window: {}, self: {} };
    vm.runInContext(script, vm.createContext(sandbox));
    return sandbox;
}

function compact(index) {
	/* https://john-millikin.com/compacting-lunr-search-indices */
	function compactInvIndex(index) {
		const fields = index["fields"];
		const fieldVectorIdxs = new Map(index["fieldVectors"].map((v, idx) => [v[0], idx]));
		const items = new Map(index["invertedIndex"].map(item => {
			const token = item[0];
			const props = item[1];
			const newItem = [token];
			fields.forEach(field => {
				const fProps = props[field];
				const matches = [];
				Object.keys(fProps).forEach(docRef => {
					const fieldVectorIdx = fieldVectorIdxs.get(`${field}/${docRef}`);
					if (fieldVectorIdx === undefined) {
						throw new Error();
					}
					matches.push(fieldVectorIdx);
					matches.push(fProps[docRef]);
				});
				newItem.push(matches);
			});
			return [props["_index"], newItem];
		}));
		const indexes = Array.from(items.keys()).sort((a, b) => a - b);
		const compacted = Array.from(indexes, k => items.get(k));
		return compacted;
	}
	function compactVectors(index) {
		return index["fieldVectors"].map(item => {
			const id = item[0];
			const vectors = item[1];
			let prev = null;
			const compacted = vectors.map((v, ii) => {
				if (ii % 2 === 0) {
					if (prev !== null && v === prev + 1) {
						prev += 1;
						return null;
					}
					prev = v;
				}
				return v;
			});
			return [id, compacted];
		});
	}
    index.invertedIndex = compactInvIndex(index);
    index.fieldVectors = compactVectors(index);
}

let lunr = (await executeScript(await loadScript(LUNR_SCRIPT)))['lunr'];

stdin.resume();
stdin.setEncoding('utf8');

stdin.on('data', function (data) {buffer.push(data)});

stdin.on('end', function () {
    const documents = JSON.parse(buffer.join(''));
    let idx = lunr(function () {
        this.ref('i');
        this.field('name', {boost: 10});
        this.field('ref', {boost: 5});
        this.field('doc');
        this.metadataWhitelist = ['position'];
        documents.forEach(function (doc, i) {
            const parts = doc.ref.split('.');
            doc['name'] = parts[parts.length - 1];
            doc['i'] = i;
            this.add(doc);
        }, this)
    })

    let out = idx.toJSON();
    compact(out);
    stdout.write(JSON.stringify([out, documents]));
})
