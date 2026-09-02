import { onRequestGet as __api_activate_js_onRequestGet } from "/home/bretstu/projects/founderledequities/functions/api/activate.js"
import { onRequestGet as __api_checkout_js_onRequestGet } from "/home/bretstu/projects/founderledequities/functions/api/checkout.js"
import { onRequestGet as __api_login_js_onRequestGet } from "/home/bretstu/projects/founderledequities/functions/api/login.js"
import { onRequestPost as __api_login_js_onRequestPost } from "/home/bretstu/projects/founderledequities/functions/api/login.js"
import { onRequestGet as __api_me_js_onRequestGet } from "/home/bretstu/projects/founderledequities/functions/api/me.js"
import { onRequestGet as __api_portal_js_onRequestGet } from "/home/bretstu/projects/founderledequities/functions/api/portal.js"
import { onRequestPost as __api_webhook_js_onRequestPost } from "/home/bretstu/projects/founderledequities/functions/api/webhook.js"
import { onRequest as __pro___path___js_onRequest } from "/home/bretstu/projects/founderledequities/functions/pro/[[path]].js"

export const routes = [
    {
      routePath: "/api/activate",
      mountPath: "/api",
      method: "GET",
      middlewares: [],
      modules: [__api_activate_js_onRequestGet],
    },
  {
      routePath: "/api/checkout",
      mountPath: "/api",
      method: "GET",
      middlewares: [],
      modules: [__api_checkout_js_onRequestGet],
    },
  {
      routePath: "/api/login",
      mountPath: "/api",
      method: "GET",
      middlewares: [],
      modules: [__api_login_js_onRequestGet],
    },
  {
      routePath: "/api/login",
      mountPath: "/api",
      method: "POST",
      middlewares: [],
      modules: [__api_login_js_onRequestPost],
    },
  {
      routePath: "/api/me",
      mountPath: "/api",
      method: "GET",
      middlewares: [],
      modules: [__api_me_js_onRequestGet],
    },
  {
      routePath: "/api/portal",
      mountPath: "/api",
      method: "GET",
      middlewares: [],
      modules: [__api_portal_js_onRequestGet],
    },
  {
      routePath: "/api/webhook",
      mountPath: "/api",
      method: "POST",
      middlewares: [],
      modules: [__api_webhook_js_onRequestPost],
    },
  {
      routePath: "/pro/:path*",
      mountPath: "/pro",
      method: "",
      middlewares: [],
      modules: [__pro___path___js_onRequest],
    },
  ]