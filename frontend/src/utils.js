const ZONE_COLORS = ["#3e7c8c", "#6f8f45", "#d9a441", "#c4544a", "#8b6fb0"];

export function colorForId(id) {
  if (id === null || id === undefined) return ZONE_COLORS[0];
  if (typeof id === "number") return ZONE_COLORS[Math.abs(id) % ZONE_COLORS.length];
  
  let num = parseInt(String(id).replace(/\D/g, ""), 10);
  if (isNaN(num)) {
    num = String(id).split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  }
  return ZONE_COLORS[Math.abs(num) % ZONE_COLORS.length];
}

export function labelForId(id) {
  if (id === null || id === undefined) return "P—";
  const str = String(id);
  if (str.startsWith("Person_")) {
    return str.replace("Person_", "P");
  }
  if (!str.toLowerCase().startsWith("p")) {
    return `P${str}`;
  }
  return str;
}
