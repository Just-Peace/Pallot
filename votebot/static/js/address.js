// The address card under "Your ballot" in the left pane, on every page: the address with
// its city, county and districts. The ballot page fills it after each lookup and remembers
// it; the other pages show the remembered one.

import { loadAddressCard, loadLastLookup } from "./picks.js";

const $ = (selector) => document.querySelector(selector);

export function showAddress({ address, place = "", districts = "", matched = "" }) {
  $("#address-line").textContent = address;
  $("#address-line").title = matched;
  $("#address-sub").textContent = place;
  $("#address-districts").textContent = districts;
}

// The remembered card for this address, or just the address if the card is for another one.
export function rememberedCard(address) {
  const card = loadAddressCard();
  return card?.address === address ? card : { address };
}

// Pages other than the ballot: the remembered address, or a link to go and enter one.
export function showRememberedAddress() {
  const address = loadLastLookup()?.address;
  $("#address-card").hidden = !address;
  $("#no-address").hidden = Boolean(address);
  if (address) showAddress(rememberedCard(address));
}
