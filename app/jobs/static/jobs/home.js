// DFHA installer home: live filter by customer last name.
// Hides non-matching cards + hides whole stages that end up empty.

(function () {
  const input = document.getElementById("job-filter");
  if (!input) return;

  const stages = document.querySelectorAll(".stage");
  const archive = document.querySelector(".archive");
  const filterEmpty = document.getElementById("filter-empty");

  function apply() {
    const q = input.value.trim().toLowerCase();
    let totalVisible = 0;

    stages.forEach((stage) => {
      const cards = stage.querySelectorAll(".card");
      let visible = 0;
      cards.forEach((card) => {
        const last = card.dataset.lastName || "";
        const first = card.dataset.firstName || "";
        const match = !q || last.includes(q) || first.includes(q);
        card.hidden = !match;
        if (match) visible++;
      });
      // Hide the whole stage when filtering and nothing matches.
      stage.hidden = q !== "" && visible === 0;
      totalVisible += visible;
    });

    if (archive) {
      const cards = archive.querySelectorAll(".card");
      let visible = 0;
      cards.forEach((card) => {
        const last = card.dataset.lastName || "";
        const first = card.dataset.firstName || "";
        const match = !q || last.includes(q) || first.includes(q);
        card.hidden = !match;
        if (match) visible++;
      });
      archive.hidden = q !== "" && visible === 0;
      totalVisible += visible;
      // Auto-expand the archive when actively filtering, since results
      // may live in there.
      if (q && visible > 0) archive.open = true;
    }

    if (filterEmpty) filterEmpty.hidden = !(q && totalVisible === 0);
  }

  input.addEventListener("input", apply);
  // Esc clears the filter.
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { input.value = ""; apply(); }
  });
})();
