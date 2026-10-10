"""Bounded read-only checks of official provider contracts after adapter edits."""
import json
import urllib.parse
from pathlib import Path

from .http import Client
from .published_usage import plos_paper, elife_history, elife_measurement, stamp_now


def main():
    client=Client(budget=8)
    config=json.loads((Path(__file__).parents[1]/'config/sources.json').read_text())
    journal=next(j for j in config['journals'] if j['id']=='plos-biology')
    query=f'eissn:"{journal["issns"][0]}" AND subject:"Neuroscience" AND doc_type:full AND -doc_partial_parent_id:[* TO *] AND article_type:"Research Article"'
    params={'q':query,'rows':1,'wt':'json','sort':'publication_date desc',
            'fl':'id,doi,title_display,author_display,publication_date,eissn,pissn,subject,doc_type,doc_partial_parent_id,counter_total_all,counter_total_month,timestamp'}
    payload=client.get('https://api.plos.org/search?'+urllib.parse.urlencode(params))
    rows=payload.get('response',{}).get('docs',[])
    if not rows:raise SystemExit('Official PLOS probe returned no rows')
    row=rows[0]
    print(json.dumps({'source':'PLOS','attribution':'Data Provided by PLOS','schema':{k:row.get(k) for k in ('id','doi','doc_type','eissn','pissn','subject','publication_date')},
                      'retrieved_at':payload.get('_retrieved_at')},ensure_ascii=False),flush=True)
    paper=plos_paper(row,journal,payload.get('_retrieved_at',stamp_now()))
    if not paper or paper['accesses']['value'] is None:raise SystemExit('Official PLOS schema did not produce a valid measured record')
    print(json.dumps({'source':'PLOS','doi':paper['doi'],'all_time_views':paper['accesses']['value'],'last_30_days':paper['accesses']['recent_30_days']['value']}),flush=True)
    article_id='108246'
    history=client.get(f'https://api.elifesciences.org/articles/{article_id}/versions')
    parsed=elife_history(history,article_id)
    if not parsed['vor_date']:raise SystemExit('Official eLife sample has no verified published VOR')
    print(json.dumps({'source':'eLife','doi':'10.7554/elife.'+article_id,**parsed}),flush=True)
    for channel in ('page-views','downloads'):
        payload=client.get(f'https://api.elifesciences.org/metrics/article/{article_id}/{channel}?by=month&per-page=1')
        measured=elife_measurement(payload,article_id,channel,payload.get('_retrieved_at',stamp_now()))
        if measured['value'] is None:raise SystemExit('Official eLife sample has no cumulative measurement')
        print(json.dumps({'source':'eLife','channel':channel,'all_versions':measured['value'],'retrieved_at':measured['observed_at']}),flush=True)


if __name__=='__main__':main()
