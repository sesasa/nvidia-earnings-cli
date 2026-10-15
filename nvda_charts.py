"""Export sourced income-statement charts from the local database."""
from html import escape
from pathlib import Path
import math
from nvda import period, reports, statement


def income_chart(db, output='charts', report_date=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    filing = next((f for f in reports(db, 40)
                   if report_date is None or f['report_date'] == report_date), None)
    if filing is None:
        raise ValueError('No matching filing. Run refresh or use status to find report dates.')
    facts = statement(db, filing, 'income')
    required = ['revenue', 'cost of revenue', 'gross profit', 'operating income', 'net income']
    missing = [n for n in required if facts[n] is None]
    if missing:
        raise ValueError('Cannot chart income: missing ' + ', '.join(missing))
    ref = facts['revenue']
    if any((facts[n]['start'], facts[n]['end'], facts[n]['unit']) !=
           (ref['start'], ref['end'], ref['unit']) for n in required):
        raise ValueError('Cannot chart income: mismatched periods or units.')
    if any(not math.isfinite(facts[n]['value']) for n in required) or ref['value'] <= 0:
        raise ValueError('Cannot chart income: values must be finite and revenue positive.')
    revenue, cost, gross, operating, net = [facts[n]['value']/1e9 for n in required]
    if abs(revenue-cost-gross) > .002:
        raise ValueError('Revenue minus cost does not reconcile to gross profit within $2 million.')
    expenses, other = gross-operating, net-operating
    margins = [100*x/revenue for x in (gross, operating, net)]
    row = db.execute('SELECT fetched FROM snapshots WHERE url LIKE ?', ('%companyfacts%',)).fetchone()
    refreshed = row[0] if row else 'unknown'
    label = period(ref)
    background, ink, muted = '#f5f7fa', '#172b42', '#53677e'
    blue, green, red = '#3879b9', '#187d71', '#c76049'
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'text.color': ink, 'text.parse_math': False, 'axes.labelcolor': muted,
                         'xtick.color': muted, 'ytick.color': muted, 'svg.fonttype': 'none'})
    fig = plt.figure(figsize=(15, 9.4), facecolor=background)
    fig.text(.055, .946, 'NVIDIA  /  INCOME STATEMENT', fontsize=12, weight='bold', color=muted)
    fig.text(.055, .894, 'How revenue becomes profit', fontsize=29, weight='bold')
    fig.text(.055, .856, f'{label.capitalize()}  |  GAAP  |  USD billions unless stated', fontsize=11)
    eps = facts.get('diluted eps')
    eps_text = f"  •  Diluted EPS ${eps['value']:.2f}" if eps and (eps['start'], eps['end']) == (ref['start'], ref['end']) else ''
    fig.text(.055, .807, f'Net income: ${net:,.3f}B  •  ${net/revenue*100:.2f} of profit per $100 of revenue{eps_text}',
             fontsize=14, weight='bold', color=green)
    ax = fig.add_axes([.065, .32, .61, .41], facecolor=background)
    ax2 = fig.add_axes([.775, .36, .16, .33], facecolor=background)
    bars = [('Revenue', 0, revenue, blue, revenue),
            ('Cost of\nrevenue', revenue, gross, red, -cost),
            ('Gross\nprofit', 0, gross, blue, gross),
            ('Operating\nexpenses¹', gross, operating, red if expenses >= 0 else green, -expenses),
            ('Operating\nincome', 0, operating, blue, operating),
            ('Other &\ntax effect²', operating, net, red if other < 0 else green, other),
            ('Net\nincome', 0, net, green, net)]
    span = max(abs(v) for b in bars for v in b[1:3]) or 1
    for i, (_, start, end, color, value) in enumerate(bars):
        ax.bar(i, abs(end-start), bottom=min(start,end), width=.65, color=color, zorder=3)
        display = f'{value:+,.3f}' if i in (1,3,5) else f'{value:,.3f}'
        ax.text(i, max(start,end)+span*.027, display, ha='center', fontsize=10, weight='bold')
        if i < len(bars)-1:
            ax.plot([i+.325,i+1-.325], [end,end], color='#a6b4c3', linewidth=1, linestyle='--')
    ax.set_xticks(range(len(bars)), [b[0] for b in bars], fontsize=10)
    ax.tick_params(axis='both', length=0, pad=9)
    ax.set_ylim(min(0,min(b[2] for b in bars))-span*.025, span*1.17)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_: f'${x:,.0f}B'))
    ax.yaxis.grid(True, color='#dce3eb', linewidth=.7)
    ax.set_axisbelow(True)
    ax.set_title('Revenue-to-profit waterfall', loc='left', fontsize=14, weight='bold', pad=19)
    ax2.set_title('Profit margins', loc='left', fontsize=14, weight='bold', pad=19)
    for i, margin in enumerate(margins):
        ax2.barh(i, margin, height=.43, color=green if i == 2 else blue)
        ax2.text(margin+2 if margin >= 0 else margin-2, i, f'{margin:.1f}%', va='center',
                 ha='left' if margin >= 0 else 'right', fontsize=12, weight='bold')
    ax2.set_yticks(range(3), ['Gross', 'Operating', 'Net'])
    ax2.invert_yaxis()
    ax2.set_xlim(min(0,min(margins)-20), max(100,max(margins)+25))
    ax2.set_xticks([0,50,100], ['0%','50%','100%'])
    ax2.tick_params(axis='both', length=0, pad=7)
    ax2.xaxis.grid(True, color='#dce3eb', linewidth=.7)
    ax2.set_axisbelow(True)
    for axis in (ax,ax2):
        for spine in axis.spines.values():
            spine.set_visible(False)
    fig.text(.055,.205,'Reading the chart',fontsize=12,weight='bold')
    notes = [
        'Blue and green bars are reported totals. Floating bars show the changes between totals.',
        f'¹ Operating expenses = gross profit − operating income = ${expenses:,.3f}B (derived).',
        f'² Other & tax effect = net income − operating income = ${other:+,.3f}B; combines non-operating items and taxes (derived).',
        'Margins = profit subtotal ÷ revenue. Selected statement lines; this is not a cash flow chart.',
        f"Source: NVIDIA {filing['form']}, filed {filing['filed']}. Database refreshed: {refreshed[:19]} UTC."]
    for i,line in enumerate(notes):
        fig.text(.055,.178-i*.025,line,fontsize=9,color=muted)
    fig.text(.055,.034,filing['url'],fontsize=8,color=blue,url=filing['url'])
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"nvda-income-{filing['report_date']}"
    paths = {ext: out/f'{stem}.{ext}' for ext in ('png','svg','html')}
    try:
        fig.savefig(paths['png'], dpi=180, facecolor=background)
        fig.savefig(paths['svg'], facecolor=background)
    finally:
        plt.close(fig)
    rows = ''.join(f'<tr><th>{escape(n.title())}</th><td>${facts[n]["value"]/1e9:,.3f}B</td></tr>' for n in required)
    paths['html'].write_text(f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NVIDIA income statement — {escape(filing['report_date'])}</title>
<style>body{{margin:0;background:#f5f7fa;color:#172b42;font:16px system-ui}}main{{max-width:1500px;margin:auto;padding:20px}}
img{{width:100%;height:auto}}a{{color:#276797}}summary{{cursor:pointer}}table{{border-collapse:collapse;margin:20px 0}}
th,td{{text-align:left;padding:8px 24px 8px 0}}footer{{padding:20px 0}}</style>
<main><img src="{paths['svg'].name}" alt="NVIDIA revenue-to-profit waterfall for {escape(label)}. Revenue ${revenue:.3f} billion; net income ${net:.3f} billion; net margin {margins[2]:.1f} percent.">
<p><a href="{paths['png'].name}" download>Download PNG</a> · <a href="{paths['svg'].name}" download>Download SVG</a></p>
<details><summary>View underlying figures and source</summary><p>{escape(label)}</p><table>{rows}</table>
<p><a href="{escape(filing['url'],quote=True)}">Original SEC filing</a></p></details>
<footer>Generated from the local database. Refresh data and rerun the chart command to update.</footer></main></html>''',encoding='utf-8')
    return paths
