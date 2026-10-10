// Mobalytics PoE2 guide extractor. Run as a bookmarklet on a guide page; copies
// JSON (format poe2-companion-guide/1) to the clipboard for pasting in the dashboard.
// extractGuide(win) is standalone so it can also be run from a browser pane.
function extractGuide(win) {
  var FORMAT_ERR = "Format halaman tidak dikenal";
  var SLOTS = ["helmet", "body", "gloves", "boots", "amulet", "belt", "leftRing", "rightRing"];
  var WEAPON_SLOTS = ["mainHand", "offHand"];
  try {
    var slug = win.location.pathname.replace(/\/+$/, "").split("/").pop();
    var queries = win.__PRELOADED_STATE__.poe2State.apollo.graphqlV2.queries;
    var q = queries.filter(function (x) {
      return x.queryKey && x.queryKey[0] === "ngf-ug-featured-document-page" && x.queryKey[2] === slug;
    })[0];
    var doc = q.state.data[0].game.documents.userGeneratedDocumentBySlug.data;
    var rawVariants = doc.data.buildVariants.values;
    if (!Array.isArray(rawVariants)) throw new Error(FORMAT_ERR);

    var titles = {};
    (doc.content || []).forEach(function (sec) {
      var kids = sec && sec.data && sec.data.childrenVariants;
      (kids || []).forEach(function (c) { if (c && c.id && c.title) titles[c.id] = c.title; });
    });

    var toItem = function (entry) {
      var ci = entry && entry.commonItem;
      if (!ci) return null;
      return {
        name: ci.name,
        item_class: ci.itemClassSlug,
        is_unique: !!ci.isUnique,
        stats: (ci.stats || []).map(function (s) { return [s.name, s.value]; }),
        mods: (ci.explicitDescriptions || []).map(function (d) {
          return { text: d.description, must_have: !!d.mustHave };
        }),
      };
    };

    var variants = rawVariants.map(function (v, i) {
      var items = {};
      var eq = v.equipment || {};
      SLOTS.forEach(function (k) {
        var it = toItem(eq[k]);
        if (it) items[k] = it;
      });
      WEAPON_SLOTS.forEach(function (k) {
        ["set1", "set2"].forEach(function (s) {
          var it = toItem(eq[k] && eq[k][s]);
          if (it) items[k + "." + s] = it;
        });
      });
      var gems = (v.skillGems && v.skillGems.gems) || [];
      var skills = gems.filter(function (g) { return g.activeSkill && g.activeSkill.name; })
        .map(function (g) { return { name: g.activeSkill.name, weapon_set: g.grantedByWeaponSet || null }; });
      return { id: v.id, title: titles[v.id] || "Variant " + (i + 1), items: items, skills: skills };
    });

    return {
      format: "poe2-companion-guide/1",
      source_url: win.location.origin + win.location.pathname,
      slug: slug,
      name: doc.data.name,
      pob_code: doc.data.pobCode || null,
      variants: variants,
    };
  } catch (e) {
    throw new Error(FORMAT_ERR);
  }
}

(function () {
  if (typeof window === "undefined" || typeof navigator === "undefined") return;
  try {
    var json = JSON.stringify(extractGuide(window));
    navigator.clipboard.writeText(json).then(
      function () { alert("Panduan disalin. Tempel di dashboard."); },
      function () { alert("Gagal menyalin ke clipboard."); }
    );
  } catch (e) {
    alert(e.message);
  }
})();
