export function blockSide(size) {
    const side=Math.sqrt(size);
    if(!Number.isInteger(size)||size<4||!Number.isInteger(side))throw new RangeError('Invalid board size');
    return side;
}
export function canonicalIndex(row,col,size,rowOrder,columnOrder) {
    blockSide(size);
    if(!Number.isInteger(row)||!Number.isInteger(col)||row<0||col<0||row>=size||col>=size)throw new RangeError('Invalid position');
    return (rowOrder?.[row]??row)*size+(columnOrder?.[col]??col);
}
export function displayPosition(index,size,rowOrder,columnOrder) {
    blockSide(size);
    if(!Number.isInteger(index)||index<0||index>=size**2)throw new RangeError('Invalid cell');
    const row=Math.floor(index/size),col=index%size;
    return {row:rowOrder?rowOrder.indexOf(row):row,col:columnOrder?columnOrder.indexOf(col):col};
}
