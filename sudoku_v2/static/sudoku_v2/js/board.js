import {renderSymbol} from './symbols.js?v=12';
import {blockSide,displayPosition} from './geometry.js?v=12';

function makeGrid(container, size, own) {
    container.replaceChildren();
    const base=blockSide(size),grid=document.createElement('div');grid.className='sudoku-board board-grid';
    grid.dataset.size=String(size);grid.dataset.own=String(own);
    grid.setAttribute('role','grid');grid.setAttribute('aria-rowcount',size);grid.setAttribute('aria-colcount',size);
    grid.style.gridTemplateColumns=`repeat(${base},minmax(0,1fr))`;
    grid.style.gridTemplateRows=`repeat(${base},minmax(0,1fr))`;
    for(let boxIndex=0;boxIndex<size;boxIndex++){
        const box=document.createElement('div');box.className='board-box';box.dataset.boxIndex=boxIndex;box.setAttribute('role','rowgroup');
        const content=document.createElement('div');content.className='box-content';content.setAttribute('role','presentation');
        content.style.gridTemplateColumns=`repeat(${base},minmax(0,1fr))`;
        content.style.gridTemplateRows=`repeat(${base},minmax(0,1fr))`;
        for(let dr=0;dr<base;dr++){
            const r=Math.floor(boxIndex/base)*base+dr;
            const row=document.createElement('div');row.className='box-row';row.dataset.rowIndex=r;row.setAttribute('role','row');
            for(let dc=0;dc<base;dc++){
            const c=(boxIndex%base)*base+dc;
            const cell=document.createElement(own?'button':'span');
            cell.className='cell';cell.dataset.cellIndex=r*size+c;
            cell.setAttribute('role','gridcell');
            if(own){cell.type='button';cell.tabIndex=-1;}
            for(const name of ['digit','cell-notes','bonus-mark']) {
                const part=document.createElement('span');part.className=name;
                if(name!=='digit')part.setAttribute('aria-hidden','true');
                cell.append(part);
            }
            row.append(cell);
            }
            content.append(row);
        }
        box.append(content);grid.append(box);
    }
    container.append(grid);return grid;
}
export function getNoteLayout(size, value) {
    const side=Math.ceil(Math.sqrt(size)),position=value-1;
    return {side,row:Math.floor(position/side)+1,column:position%side+1};
}
export function renderBoard(container, board, {config,selectedCell=null,highlightValue}) {
    const own=board.name===config.username,size=board.size??9;
    const base=blockSide(size),existing=container.querySelector('.board-grid');
    const table=existing?.dataset.size===String(size)&&existing.dataset.own===String(own)?existing:makeGrid(container,size,own);
    table.dataset.boardName=board.name;table.setAttribute('aria-label',`${own?'Моя доска':'Доска игрока'} ${board.name}`);
    const fixed=new Set(board.fixedCells??[]),wrong=new Set(board.wrongCells??[]);
    const selectedValue=highlightValue??board.values?.[selectedCell]??'';
    const selectedPosition=Number.isInteger(selectedCell)&&selectedCell>=0&&selectedCell<size**2?
        displayPosition(selectedCell,size,board.rowOrder,board.columnOrder):null;
    for(const row of table.querySelectorAll('.box-row')){
        const position=displayPosition(Number(row.dataset.rowIndex)*size,size,board.rowOrder,board.columnOrder);
        row.setAttribute('aria-rowindex',position.row+1);
    }
    for(const cell of table.querySelectorAll('[data-cell-index]')) {
        const i=Number(cell.dataset.cellIndex),{row:r,col:c}=displayPosition(i,size,board.rowOrder,board.columnOrder),value=board.values?.[i]??'';
        cell.style.gridArea=`${r%base+1} / ${c%base+1}`;
        cell.setAttribute('aria-rowindex',r+1);cell.setAttribute('aria-colindex',c+1);
        const selected=own&&i===selectedCell;
        const related=own&&selectedPosition&&(r===selectedPosition.row||c===selectedPosition.col||
            (Math.floor(r/base)===Math.floor(selectedPosition.row/base)&&Math.floor(c/base)===Math.floor(selectedPosition.col/base)));
        cell.classList.toggle('is-fixed',fixed.has(i));cell.classList.toggle('is-selected',selected);
        cell.classList.toggle('is-related',related);
        cell.classList.toggle('is-matching',own&&value!==''&&value===selectedValue);
        cell.classList.toggle('is-error',config.preferences.showErrors&&wrong.has(i));
        cell.dataset.fixed=String(fixed.has(i));cell.dataset.value=String(value);
        if(own){cell.tabIndex=(i===(selectedCell??0))?0:-1;cell.setAttribute('aria-pressed',String(selected));}
        const digit=cell.querySelector('.digit');
        renderSymbol(digit,value,config.runtime.symbolSheet);
        const notes=cell.querySelector('.cell-notes');
        const candidates=own&&value===''?(config.local.notes[i]??[]).filter(n=>Number.isInteger(n)&&n>=1&&n<=size):[];
        const side=Math.ceil(Math.sqrt(size));
        const notesSignature=`${side}:${candidates.join(',')}`;
        if(notes.dataset.values!==notesSignature){
            notes.replaceChildren();
            notes.style.gridTemplateColumns=`repeat(${side},minmax(0,1fr))`;
            notes.style.gridTemplateRows=`repeat(${side},minmax(0,1fr))`;
            for(const note of candidates) {
                const {row,column}=getNoteLayout(size,note);
                const n=document.createElement('span');n.textContent=note;
                n.style.gridArea=`${row} / ${column}`;
                notes.append(n);
            }
            notes.dataset.values=notesSignature;
        }
        const bonus=board.bonuses?.[i],definition=config.runtime.bonusCatalog?.find(b=>b.id===bonus);
        const mark=cell.querySelector('.bonus-mark'),bonusSymbol=bonus?(definition?.symbol??'◇'):'';
        if(mark.textContent!==bonusSymbol)mark.textContent=bonusSymbol;
        const bonusLabel=bonus?`Бонус: ${definition?.label??bonus}`:'';
        cell.setAttribute('aria-label',`Строка ${r+1}, столбец ${c+1}: ${value===''?'пусто':value}${candidates.length?', заметки: '+candidates.join(', '):''}${fixed.has(i)?', исходная':''}${config.preferences.showErrors&&wrong.has(i)?', ошибка':''}${bonusLabel?', '+bonusLabel:''}`);
    }
    let completion=container.querySelector('.completion-overlay');
    if(!completion){
        completion=document.createElement('div');completion.className='completion-overlay';
        completion.setAttribute('role','status');
        const label=document.createElement('strong');label.textContent='Готово!';completion.append(label);
        container.append(completion);
    }
    completion.hidden=!board.completed;
    container.classList.toggle('is-completed',Boolean(board.completed));
    return table;
}
