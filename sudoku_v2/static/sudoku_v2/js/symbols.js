export function getSpriteRect(width,height,value) {
    const sy=(value-1)*width;
    return {sx:0,sy,sw:width,sh:Math.max(0,Math.min(width,height-sy)),size:width};
}
export async function loadSymbolSheet(source) {
    const image=new Image();
    const url=source instanceof Blob?URL.createObjectURL(source):source;
    try {
        image.src=url;await image.decode();
        return {image,width:image.naturalWidth,height:image.naturalHeight,tiles:new Map()};
    } finally { if(source instanceof Blob)URL.revokeObjectURL(url); }
}
export function renderSymbol(element,value,sheet=null) {
    if(element.symbolSheet===sheet && element.symbolValue===value)return;
    element.symbolSheet=sheet;element.symbolValue=value;element.replaceChildren();
    if(!sheet || !Number.isInteger(value) || value<1) {element.textContent=String(value);return;}
    if(!sheet.tiles.has(value)) {
        const tile=document.createElement('canvas');tile.width=tile.height=128;
        const ctx=tile.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,128,128);
        const r=getSpriteRect(sheet.width,sheet.height,value);
        if(r.sh>0)ctx.drawImage(sheet.image,r.sx,r.sy,r.sw,r.sh,0,0,128,128*r.sh/r.size);
        sheet.tiles.set(value,tile);
    }
    const canvas=document.createElement('canvas');canvas.width=canvas.height=128;
    canvas.setAttribute('aria-hidden','true');canvas.getContext('2d').drawImage(sheet.tiles.get(value),0,0);
    element.append(canvas);
}
export function disposeSymbolSheet(sheet) { sheet?.tiles.clear(); }
