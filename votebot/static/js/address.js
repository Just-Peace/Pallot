// The address card under "Your ballot" in the left pane, on every page: the address with
// its city and county, and the election. The ballot page fills it after each lookup and remembers it; the
// other pages show the remembered one. On a phone the top bar's button shows it too.

import { $ } from "./dom.js";
import { ADDRESS_CARD, LAST_LOOKUP, readJson } from "./storage.js";
import { setTopBarAddress } from "./topbar.js";

export function showAddress({ address, place = "", matched = "", election = "" }) {
  $("#address-line").textContent = address;
  $("#address-line").title = matched;
  $("#address-sub").textContent = place;
  $("#address-election").textContent = election;
  $("#address-election").hidden = !election;
  setTopBarAddress(address);
}

// The remembered card for this address, or just the address if the card is for another one.
export function rememberedCard(address) {
  const card = readJson(ADDRESS_CARD, null);
  return card?.address === address ? card : { address };
}

// Pages other than the ballot: the remembered address, or a link to go and enter one.
export function showRememberedAddress() {
  const address = readJson(LAST_LOOKUP, null)?.address;
  $("#address-card").hidden = !address;
  $("#no-address").hidden = Boolean(address);
  if (address) showAddress(rememberedCard(address));
  else setTopBarAddress("");
}
