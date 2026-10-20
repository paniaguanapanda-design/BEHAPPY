import React from "react";
import { View } from "react-native";
import { Image } from "expo-image";
import Animated, { FadeIn } from "react-native-reanimated";
import { makeStyles } from "@/src/theme";

const SPLASH = require("@/assets/images/behappy-splash.png");

export function AppSplash() {
  const styles = useStyles();
  return (
    <View style={styles.root} testID="app-splash">
      <Animated.View entering={FadeIn.duration(500)} style={styles.wrap}>
        <Image source={SPLASH} style={styles.img} contentFit="contain" />
      </Animated.View>
    </View>
  );
}

const useStyles = makeStyles(() => ({
  // Background must match the native splash/logo background exactly in any theme
  root: { flex: 1, backgroundColor: "#F8F5EE", alignItems: "center", justifyContent: "center" },
  wrap: { width: "80%", maxWidth: 360, aspectRatio: 688 / 640 },
  img: { width: "100%", height: "100%" },
}));
