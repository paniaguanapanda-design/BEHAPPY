const { withGradleProperties } = require("expo/config-plugins");

// The APK offered on the website (EAS "preview" profile) is built only for 64-bit ARM phones
// (practically every Android phone of the last years), so it downloads much faster.
// The Google Play build keeps every architecture: Play sends each phone only what it needs.
const withArm64Only = (cfg) =>
  withGradleProperties(cfg, (c) => {
    c.modResults = c.modResults.filter((p) => !(p.type === "property" && p.key === "reactNativeArchitectures"));
    c.modResults.push({ type: "property", key: "reactNativeArchitectures", value: "arm64-v8a" });
    return c;
  });

// Adds secrets that must not live in app.json. The Google Maps key for the hardware-store map comes from the
// EAS environment variable GOOGLE_MAPS_ANDROID_API_KEY (set it in expo.dev > project > Environment variables).
module.exports = ({ config }) => {
  const key = process.env.GOOGLE_MAPS_ANDROID_API_KEY;
  const out = {
    ...config,
    // The map screen only draws the Google map when the key was in the build; otherwise it shows the list alone.
    extra: { ...(config.extra ?? {}), hasMapsKey: Boolean(key) },
    android: {
      ...config.android,
      config: { ...(config.android?.config ?? {}), ...(key ? { googleMaps: { apiKey: key } } : {}) },
    },
  };
  return process.env.APK_ARM64_ONLY === "1" ? withArm64Only(out) : out;
};
