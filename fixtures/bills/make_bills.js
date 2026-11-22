// Regenerates the synthetic test bills in this folder (needs Playwright + Chromium).
//   node fixtures/bills/make_bills.js
// Everything is fictional. These are rendered pages styled to look like bills, NOT photographs of
// real merchant bills and not real handwriting; use real photos for a true accuracy measurement.
const { chromium } = require('playwright');
const path = require('path');
const out = __dirname;

const paper = (body, extra = '') => `<html><head><meta charset="utf-8"><style>
  body{margin:0;background:#cfc8b8;font-family:FreeSerif,serif}
  .sheet{width:760px;margin:40px auto;padding:36px 44px 60px;background:#fbf6e6;
    background-image:repeating-linear-gradient(#fbf6e6 0 43px,#c9d6e6 43px 45px);box-shadow:0 8px 30px #0005}
  .hand{font-style:italic;color:#1d2a78;font-size:30px;line-height:45px;letter-spacing:.5px}
  .hand .r{display:grid;grid-template-columns:1fr 70px 110px 120px;gap:8px}
  .hand .r span:nth-child(n+2){text-align:right}
  .head{text-align:center;font-size:36px;font-weight:bold;font-style:normal}
  .w1{transform:rotate(-1.2deg)} .w2{transform:rotate(.8deg)} .w3{transform:rotate(-.5deg)}
  .smudge{display:inline-block;width:46px;height:30px;border-radius:50%;background:#2a3170;filter:blur(3px);vertical-align:middle}
  ${extra}</style></head><body>${body}</body></html>`;

const BILLS = {
  'english-handwritten.png': { html: paper(`<div class="sheet hand">
      <div class="head">SRI LAKSHMI TRADERS</div><div style="text-align:center">Cash / Credit Bill</div>
      <div class="w1">To: Murugan Stores &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: 18/11/2026</div><div>&nbsp;</div>
      <div class="r"><span>Item</span><span>Qty</span><span>Rate</span><span>Amt</span></div>
      <div class="r w2"><span>Ponni rice 25kg bag</span><span>2</span><span>1200</span><span>2400</span></div>
      <div class="r w3"><span>Toor dal 1kg</span><span>5</span><span>160</span><span>850</span></div>
      <div class="r w1"><span>Sunflower oil 5L can</span><span>3</span><span>640</span><span>1920</span></div>
      <div class="r w2"><span>Sugar 50kg bag</span><span>1</span><span>2100</span><span>2100</span></div>
      <div>&nbsp;</div><div class="r"><span></span><span></span><span>Total</span><span>Rs. 7270/-</span></div>
      <div class="w3">Balance next week pls.</div></div>`) },
  'tamil-handwritten.png': { html: paper(`<div class="sheet hand">
      <div class="head">ஸ்ரீ லக்ஷ்மி டிரேடர்ஸ்</div><div style="text-align:center">ரொக்கம் / கடன் பில்</div>
      <div class="w2">பெறுநர்: அன்பு ப்ரொவிஷன் ஸ்டோர் &nbsp;&nbsp; தேதி: 17/11/2026</div><div>&nbsp;</div>
      <div class="r"><span>பொருள்</span><span>அளவு</span><span>விலை</span><span>தொகை</span></div>
      <div class="r w1"><span>அரிசி 25 கிலோ மூட்டை</span><span>4</span><span>1250</span><span>5000</span></div>
      <div class="r w3"><span>துவரம் பருப்பு 1 கிலோ</span><span>10</span><span>165</span><span>1650</span></div>
      <div class="r w2"><span>சர்க்கரை 1 கிலோ</span><span>20</span><span>46</span><span>920</span></div>
      <div class="r w1"><span>நல்லெண்ணெய் 1 லிட்டர்</span><span>6</span><span>310</span><span>1860</span></div>
      <div>&nbsp;</div><div class="r"><span></span><span></span><span>மொத்தம்</span><span>ரூ. 9430</span></div></div>`) },
  'printed-tax-invoice.pdf': { pdf: true, html: `<html><head><meta charset="utf-8"><style>
      body{font-family:FreeSans,sans-serif;font-size:13px;margin:40px;color:#111} h1{font-size:20px;margin:0}
      table{width:100%;border-collapse:collapse;margin-top:14px} th,td{border:1px solid #777;padding:6px 8px}
      td:nth-child(n+3),th:nth-child(n+3){text-align:right} .tot td{font-weight:bold}</style></head><body>
      <h1>COASTAL WHOLESALE AGENCIES</h1><div>14, Market Road, Nagapattinam 611001 &nbsp; GSTIN: 33ABCDE1234F1Z5 (sample)</div>
      <h2 style="font-size:15px">TAX INVOICE &nbsp; No. CW/2026/0412 &nbsp; Date: 16-11-2026</h2>
      <div><b>Bill To:</b> Kavitha Supermarket, Velankanni Road</div>
      <table><tr><th>#</th><th>Description</th><th>Qty</th><th>Rate (Rs)</th><th>Amount (Rs)</th></tr>
      <tr><td>1</td><td>Tea dust 1 kg pack</td><td>12</td><td>700.00</td><td>8,400.00</td></tr>
      <tr><td>2</td><td>Detergent powder 5 kg</td><td>8</td><td>450.00</td><td>3,600.00</td></tr>
      <tr><td>3</td><td>Biscuit carton (24 pcs)</td><td>5</td><td>1,150.50</td><td>5,752.50</td></tr>
      <tr><td colspan="4">Sub Total</td><td>17,752.50</td></tr>
      <tr><td colspan="4">CGST 2.5% + SGST 2.5%</td><td>887.63</td></tr>
      <tr class="tot"><td colspan="4">Grand Total</td><td>18,640.13</td></tr></table>
      <p>Goods once sold will not be taken back. This is a fictional sample.</p></body></html>` },
  'mixed-creased-dim.jpg': { jpeg: 55, html: paper(`<div class="sheet hand" style="transform:rotate(5deg) skewX(-3deg);filter:blur(1.1px) contrast(.72) brightness(.78)">
      <div class="head">SRI LAKSHMI TRADERS</div>
      <div class="w1">To: பாண்டியன் டீ ஸ்டால் (Pandian Tea Stall) &nbsp; 15/11/2026</div><div>&nbsp;</div>
      <div class="r w2"><span>Tea dust 1kg</span><span>6</span><span>700</span><span>4200</span></div>
      <div class="r w3"><span>பால் பவுடர் (milk powder) 1kg</span><span>3</span><span>520</span><span>1560</span></div>
      <div class="r w1"><span>Sugar 1kg</span><span>15</span><span>46</span><span>690</span></div>
      <div>&nbsp;</div><div class="r"><span></span><span></span><span>Total</span><span>6450</span></div></div>
      <div style="position:fixed;inset:0;background:linear-gradient(115deg,transparent 40%,#0003 52%,transparent 64%)"></div>`) },
  'smudged-cut-off.jpg': { jpeg: 70, clip: { x: 0, y: 0, width: 860, height: 425 }, html: paper(`<div class="sheet hand">
      <div class="head">SRI LAKSHMI TRADERS</div>
      <div class="w3">To: Bay Retail &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Date: 14/11</div><div>&nbsp;</div>
      <div class="r w1"><span>Atta 10kg bag</span><span>8</span><span>500</span><span>4000</span></div>
      <div class="r w2"><span>Groundnut oil 15L tin</span><span><i class="smudge"></i></span><span>2850</span><span></span></div>
      <div class="r w3"><span>Salt 1kg</span><span>30</span><span>22</span><span>660</span></div>
      <div class="r w1"><span>Red chilli 1kg</span><span>4</span><span>280</span><span>1120</span></div>
      <div>&nbsp;</div><div class="r"><span></span><span></span><span>Total</span><span>14330</span></div></div>`) },
  'not-a-bill.png': { html: `<html><body style="margin:0;background:#0a6b4d;color:#fff;font-family:FreeSans;display:flex;align-items:center;justify-content:center;height:600px">
      <div style="text-align:center"><div style="font-size:54px;font-weight:bold">Deepavali Offer!</div><div style="font-size:28px">Sri Lakshmi Traders · Open 7 am to 9 pm</div></div></body></html>` },
};

(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 860, height: 900 }, deviceScaleFactor: 1.5 })).newPage();
  for (const [name, b] of Object.entries(BILLS)) {
    await page.setContent(b.html); await page.waitForTimeout(200);
    const file = path.join(out, name);
    if (b.pdf) await page.pdf({ path: file, format: 'A4' });
    else await page.screenshot({ path: file, fullPage: !b.clip, clip: b.clip, type: b.jpeg ? 'jpeg' : 'png', quality: b.jpeg });
    console.log('wrote', name);
  }
  await browser.close();
})();
