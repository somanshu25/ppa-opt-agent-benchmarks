"""Pull selected slides out of the deck into a standalone page.

Used to eyeball individual chart slides at full size: the deck is one long
scrolling document, so a headless screenshot of the whole thing is unreadable
and fragment-scrolling lands unpredictably.
"""

import re
import sys

src, dst = sys.argv[1], sys.argv[2]
wanted = sys.argv[3:]

html = open(src, encoding="utf-8").read()
head = html.split("<body>")[0]
sections = re.findall(r'<section class="slide"[^>]*>.*?</section>', html, re.S)

picked = [s for s in sections
          if any('id="{}"'.format(w) in s for w in wanted)] if wanted else sections

with open(dst, "w", encoding="utf-8") as fh:
    fh.write(head + "<body>\n" + "\n".join(picked) + "\n</body></html>")

print("extracted {} of {} slides -> {}".format(len(picked), len(sections), dst))
