import re
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("pdf-ctdt")
OUT.mkdir(exist_ok=True)


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|]', "", s).strip()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})

    page.goto("https://sv.dut.udn.vn/G_ListCTDT.aspx", wait_until="networkidle")
    page.click("#MainContent_GListCTDT_btnDuLieu")
    page.wait_for_selector("tr.GridRow")

    rows = page.eval_on_selector_all(
        "tr.GridRow",
        """
        trs => trs.map((tr, index) => {
            const td = [...tr.querySelectorAll("td")].map(x => x.innerText.trim());
            const onclick = tr.getAttribute("onclick") || "";
            const year = Number((td[3]?.match(/K(\\d{4})/i) || [])[1] || 0);
            return {
                index,
                onclick,
                ma: td[5],
                ten: td[3],
                year
            };
        }).filter(x => x.onclick.includes("CTDT_LoadKhung") && x.year >= 2022)
        """,
    )

    print(f"Co {len(rows)} CTDT tu K2022 tro len")

    for i, item in enumerate(rows, 1):
        idx = item["index"]
        ma = item["ma"]
        ten = item["ten"]

        print(f"[{i}/{len(rows)}] {ma} - {ten}")

        page.eval_on_selector_all(
            "tr.GridRow",
            f"""
            trs => trs[{idx}].querySelector("td.View").click()
            """,
        )

        page.wait_for_selector("#G_KhungCTDT_Grid", timeout=10000)

        html = page.evaluate("""
            () => {
                const info = document.querySelector("#G_KhungCTDT_Grid0").cloneNode(true);
                const table = document.querySelector("#G_KhungCTDT_Grid").cloneNode(true);

                [info, table].forEach(t => {
                    t.querySelectorAll("td.GridCheck").forEach(td => {
                        td.textContent = "✓";
                        td.style.textAlign = "center";
                        td.style.color = "#2563eb";
                        td.style.fontWeight = "bold";
                    });
                });

                return `
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {
  size: A3 landscape;
  margin: 8mm;
}
body {
  font-family: "Times New Roman", serif;
  margin: 0;
}
h3 {
  text-align: center;
  margin: 0 0 6px 0;
  font-size: 16px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 8px;
  margin-bottom: 6px;
}
tr {
  break-inside: avoid;
}
th, td {
  border: 1px solid #000;
  padding: 2px 3px;
  vertical-align: middle;
  white-space: normal;
}
th {
  text-align: center;
  font-weight: bold;
}
</style>
</head>
<body>
<h3>KHUNG CHƯƠNG TRÌNH ĐÀO TẠO</h3>
${info.outerHTML}
${table.outerHTML}
</body>
</html>`;
            }
            """)

        pdf_page = browser.new_page()
        pdf_page.set_content(html, wait_until="networkidle")

        filename = f"Khung CTDT-{safe_name(ma)}-{safe_name(ten)}.pdf"

        pdf_page.pdf(
            path=str(OUT / filename),
            format="A3",
            landscape=True,
            print_background=True,
            margin={
                "top": "8mm",
                "right": "8mm",
                "bottom": "8mm",
                "left": "8mm",
            },
        )

        pdf_page.close()

        try:
            page.click(".ui-dialog-titlebar-close")
        except:
            pass

    browser.close()

print("Xong. PDF nam trong thu muc pdf-ctdt")
