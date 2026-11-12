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

  useEffect(() => {
    function handlePopState() {
      setPathname(browser.location.pathname);
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
      browser.scrollTo?.(0, 0);
    },
    [browser],
  );

  const value = useMemo(
    () => ({ browser, pathname, navigate, ...matchRoute(pathname) }),
    [browser, pathname, navigate],
  );
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

function useRouter() {
  const router = useContext(RouterContext);
  if (!router) throw new Error("Routing needs a <RouterProvider> above it.");
  return router;
}

/** The current `{ pathname, route, params }`. */
export function useRoute() {
  const { pathname, route, params } = useRouter();
  return { pathname, route, params };
}

export function useNavigate() {
  return useRouter().navigate;
}

function isPlainLeftClick(event) {
  return (
    event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
  );
}

/**
 * A real anchor. A plain click inside the rebuilt application is handled
 * without a page load; anything else (new tab, a modifier key, a path outside
 * the application such as /dashboard/legacy) is left to the browser.
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
