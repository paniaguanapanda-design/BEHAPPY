// Small hand-offs between the public screens (login, /pro) and the auth gate.

// Set by the specialists page: the login screen opens in "create account" mode for a specialist.
let proIntent = false;
export const setProIntent = () => {
  proIntent = true;
};
export const takeProIntent = () => {
  const v = proIntent;
  proIntent = false;
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
