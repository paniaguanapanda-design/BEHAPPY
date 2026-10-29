// Small hand-offs between the public screens (login, /pro) and the auth gate.

// Set by the specialists page: the login screen opens for a specialist ("up" = create account, "in" = sign in).
// Either way the profile form opens right after: it is the only way into it, since clients don't see it.
let proIntent: "up" | "in" | null = null;
export const setProIntent = (mode: "up" | "in" = "up") => {
  proIntent = mode;
};
export const takeProIntent = () => {
  const v = proIntent;
  proIntent = null;
  return v;
};

// Where to go right after signing in (the gate reads it once). null = home.
let afterLogin: string | null = null;
export const setAfterLogin = (route: string | null) => {
  afterLogin = route;
};
export const takeAfterLogin = () => {
  const v = afterLogin;
  afterLogin = null;
  return v;
};
