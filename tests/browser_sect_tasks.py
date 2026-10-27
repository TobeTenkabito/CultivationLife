"""Actual task/donation/governance clicks, stale recovery and narrow layouts."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.rules import add_item
from cultivation_life.system.sect_tasks import state,tasks
from cultivation_life.system.sect_tasks.finance import salaries
from test_sect_tasks import ready
from scripts.browser_navigation import navigation_locator,set_theme
from playwright.sync_api import sync_playwright


def main():
    output=ROOT/'build/sect-tasks-ui';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        e,g,sect,finance=ready.__wrapped__(Path(folder))
        key=next(iter(state.ordinary('human')));good=state.ordinary('human')[key]
        tasks.publish(g,sect,'sect-high','material',key)
        add_item(g.player,good['id'],1)
        salaries(g,sect,finance)
        e.store.save(g)
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960));errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    base=f'http://127.0.0.1:{http.server_port}'
                    page.goto(base);page.wait_for_function('!!configData&&!busy');page.evaluate('id=>loadGame(id)',g.id)
                    page.wait_for_function('!!game?.faction?.task_board&&!busy')
                    navigation_locator(page,'[data-panel-target=faction]').click()
                    page.locator('#faction-content [data-subpage="任务"]').click()
                    board=page.locator('#sect-task-board')
                    board.locator('[data-sect-action=complete]').click()
                    page.wait_for_function('!busy&&game.faction.task_board.tasks[0].status==="completed"')
                    board.locator('[data-tab=treasury]').click()
                    old=page.evaluate('game.faction.task_board.revision')
                    board.locator('[data-sect-action=donate]').click()
                    page.wait_for_function('r=>!busy&&game.faction.task_board.revision>r',arg=old)
                    revision=page.evaluate('game.faction.task_board.revision')
                    response=page.request.post(base+f'/api/games/{g.id}/sect-task',data=dict(action='donate',owner_id=sect.id,revision=revision,amount=100))
                    assert response.ok
                    board.locator('[data-sect-action=donate]').click()
                    page.wait_for_function('r=>!busy&&game.faction.task_board.revision===r',arg=revision+1)
                    board.locator('[data-tab=governance]').click()
                    board.locator('[data-sect-action=recruitment]').click()
                    page.wait_for_function('!busy&&!game.faction.task_board.recruitment_open')
                    board.locator('[data-tab=finance]').click()
                    assert '低阶门人' in board.inner_text()
                    for theme in ['a','b','d','f']:
                        set_theme(page,theme)
                        for width,height in [(1440,960),(390,844),(320,740)]:
                            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(250)
                            for tab in ['tasks','publish','treasury','finance','governance']:
                                board.locator(f'[data-tab={tab}]').click()
                                assert board.evaluate('n=>n.scrollWidth<=n.clientWidth+2'),(theme,width,tab)
                            if theme=='a':page.screenshot(path=str(output/f'board-{width}.png'))
                    current=e.store.load(g.id);current.pending_event=e._instantiate_event(e.events_by_id['EVT_SECT_FINANCE_CONFLICT'],current,__import__('random').Random(1));e.store.save(current)
                    page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy&&!!game.pending_event')
                    board.locator('[data-tab=treasury]').click()
                    assert board.locator('[data-sect-action=donate]').is_disabled()
                    # Real event submission leaves the task commands usable again.
                    page.locator('#faction-toggle').click()
                    page.locator('#event-choices button').click()
                    page.wait_for_function('!busy&&!game.pending_event')
                    navigation_locator(page,'[data-panel-target=faction]').click()
                    assert not board.locator('[data-sect-action=donate]').is_disabled()
                    page.locator('#faction-toggle').click()
                    # Simulate an already-open legacy page while the saved event
                    # still contains an earned follow-up. Submit through the UI.
                    import random
                    current=e.store.load(g.id)
                    legacy=e._instantiate_event(e.events_by_id['EVT_FACTION_COMMON_PATROL_001'],current,random.Random(1))
                    reward=e._prepare_treasure_reward_event(current,random.Random(2))
                    legacy['_followup_event']=reward;current.pending_event=legacy;e.store.save(current)
                    page.evaluate('event=>{game.pending_event=event;renderEvent();}',legacy)
                    page.locator('#event-choices button').first.click()
                    page.wait_for_function('id=>!busy&&game.pending_event?.id===id',arg=reward['id'])
                    page.locator('#event-choices button').first.click()
                    page.wait_for_function('!busy&&!game.pending_event')
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Sect tasks: real completion, donation, stale recovery, governance, event unblock; four themes / desktop / narrow mobile passed.')


if __name__=='__main__':main()
