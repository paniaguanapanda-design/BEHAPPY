// Adds secrets that must not live in app.json. The Google Maps key for the hardware-store map comes from the
// EAS environment variable GOOGLE_MAPS_ANDROID_API_KEY (set it in expo.dev > project > Environment variables).
module.exports = ({ config }) => {
  const key = process.env.GOOGLE_MAPS_ANDROID_API_KEY;
  return {
    ...config,
    // The map screen only draws the Google map when the key was in the build; otherwise it shows the list alone.
    extra: { ...(config.extra ?? {}), hasMapsKey: Boolean(key) },
    android: {
      ...config.android,
      config: { ...(config.android?.config ?? {}), ...(key ? { googleMaps: { apiKey: key } } : {}) },
    },
  };
};
