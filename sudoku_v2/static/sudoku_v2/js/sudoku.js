import {SudokuConfig} from './config.js?v=12';
import {createGameState} from './state.js?v=12';
import {connectWebsocket} from './network.js?v=12';
import {mountGame} from './ui.js?v=17';

const bootstrap=JSON.parse(document.getElementById('sudoku-bootstrap').textContent);
const config=new SudokuConfig(bootstrap);
const store=createGameState(config);
const network=connectWebsocket({store,config});
const ui=mountGame(document.getElementById('game-app'),{store,config,network});
window.addEventListener('pagehide',()=>{ui.dispose();network.dispose();});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
