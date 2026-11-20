import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { isAppPath } from "./paths";
import { matchRoute } from "./routes";

const RouterContext = createContext(null);

/**
 * Path-based routing over the History API. No router library (ADR-0020,
 * decision 4). Back and forward work because every navigation is a history
 * entry and `popstate` re-reads the location.
 */
export function RouterProvider({ browser = window, children }) {
  const [pathname, setPathname] = useState(() => browser.location.pathname);
  // The query names something on the page (a run picked on a task's Activity).
  const [search, setSearch] = useState(() => browser.location.search ?? "");

  useEffect(() => {
    function handlePopState() {
      setPathname(browser.location.pathname);
      setSearch(browser.location.search ?? "");
    }
    browser.addEventListener("popstate", handlePopState);
    return () => browser.removeEventListener("popstate", handlePopState);
  }, [browser]);

  const navigate = useCallback(
    (href) => {
      const url = new URL(href, browser.location.href);
      if (!isAppPath(url.pathname)) {
        browser.location.assign(url.href);
        return;
      }
      const target = `${url.pathname}${url.search}${url.hash}`;
      const current = `${browser.location.pathname}${browser.location.search}${browser.location.hash}`;
      if (target !== current) {
        browser.history.pushState({}, "", target);
      }
      setPathname(url.pathname);
      setSearch(url.search);
      browser.scrollTo?.(0, 0);
    },
    [browser],
  );

  const value = useMemo(
    () => ({ browser, pathname, search, navigate, ...matchRoute(pathname) }),
    [browser, pathname, search, navigate],
  );
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

function useRouter() {
  const router = useContext(RouterContext);
  if (!router) throw new Error("Routing needs a <RouterProvider> above it.");
  return router;
}

/** The current `{ pathname, route, params, query }`; `query` is a URLSearchParams. */
export function useRoute() {
  const { pathname, search, route, params } = useRouter();
  const query = useMemo(() => new URLSearchParams(search), [search]);
  return { pathname, route, params, query };
}

export function useNavigate() {
  return useRouter().navigate;
}

/** `navigate`, or null outside a router (a component drawn on its own in a test). */
export function useOptionalNavigate() {
  return useContext(RouterContext)?.navigate ?? null;
}

function isPlainLeftClick(event) {
  return (
    event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
  );
}

/**
 * A real anchor. A plain click inside the rebuilt application is handled
 * without a page load; anything else (new tab, a modifier key, a path outside
 * the application) is left to the browser.
 */
export const Link = React.forwardRef(function Link({ href, onClick, target, children, ...rest }, ref) {
  const { browser, navigate } = useRouter();

  function handleClick(event) {
    onClick?.(event);
    if (event.defaultPrevented || !isPlainLeftClick(event) || (target && target !== "_self")) {
      return;
    }
    const url = new URL(href, browser.location.href);
    if (url.origin !== browser.location.origin || !isAppPath(url.pathname)) return;
    event.preventDefault();
    navigate(href);
  }

  return (
    <a ref={ref} href={href} target={target} onClick={handleClick} {...rest}>
      {children}
    </a>
  );
});
