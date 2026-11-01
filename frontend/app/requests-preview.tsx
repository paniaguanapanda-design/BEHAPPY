import React, { useState } from "react";
import { Image, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { makeStyles, useTheme, fonts } from "@/src/theme";

const requests = [
  {
    category: "Fontanería",
    categoryIcon: "water-outline" as const,
    age: "Hace 12 min",
    title: "Fuga debajo del fregadero",
    description: "Gotea al abrir el grifo. Me gustaría repararlo esta semana.",
    image: {
      uri: "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Ceiling_water_damage.jpg/1280px-Ceiling_water_damage.jpg",
    },
    quotes: 3,
    budget: "Desde 85 €",
    notified: "6 especialistas avisados",
    tint: "#E7F5F8",
    iconColor: "#16758A",
    initials: ["MF", "GL", "AR"],
  },
  {
    category: "Pintura",
    categoryIcon: "color-palette-outline" as const,
    age: "Hace 1 h",
    title: "Pintar el dormitorio",
    description: "Habitación de unos 16 m². Quiero cambiar el color y tapar algunos agujeros.",
    image: require("../assets/images/login-hero.jpg"),
    quotes: 1,
    budget: "Desde 120 €",
    notified: "4 especialistas avisados",
    tint: "#FFF1E6",
    iconColor: "#B9570A",
    initials: ["LC"],
  },
];

function RequestCard({ item }: { item: (typeof requests)[number] }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.card}>
      <View style={styles.cardMeta}>
        <View style={[styles.categoryIcon, { backgroundColor: item.tint }]}>
          <Ionicons name={item.categoryIcon} size={16} color={item.iconColor} />
        </View>
        <Text style={styles.category}>{item.category}</Text>
        <Text style={styles.dot}>·</Text>
        <Text style={styles.age}>{item.age}</Text>
        <Pressable accessibilityLabel="Más opciones" style={styles.more}>
          <Ionicons name="ellipsis-horizontal" size={19} color={colors.muted} />
        </Pressable>
      </View>

      <Text style={styles.cardTitle}>{item.title}</Text>
      <Text style={styles.description}>{item.description}</Text>

      <View style={styles.photoWrap}>
        <Image source={item.image} style={styles.photo} resizeMode="cover" />
        <View style={styles.distance}>
          <Ionicons name="location" size={13} color={colors.onSurfaceInverse} />
          <Text style={styles.distanceText}>Solo ciudad</Text>
        </View>
        <View style={styles.photoCount}>
          <Ionicons name="images-outline" size={13} color={colors.onSurfaceInverse} />
          <Text style={styles.photoCountText}>2 fotos</Text>
        </View>
      </View>

      <View style={styles.quoteRow}>
        <View style={styles.avatars}>
          {item.initials.map((initials, index) => (
            <View
              key={initials}
              style={[
                styles.avatar,
                { marginLeft: index ? -8 : 0, backgroundColor: ["#D8E9E3", "#E9DDF0", "#F5E0CF"][index % 3] },
              ]}
            >
              <Text style={styles.avatarText}>{initials}</Text>
            </View>
          ))}
        </View>
        <Text style={styles.quoteText}>
          <Text style={styles.quoteNumber}>{item.quotes} </Text>
          {item.quotes === 1 ? "presupuesto recibido" : "presupuestos recibidos"}
        </Text>
      </View>

      <View style={styles.cardFooter}>
        <View style={styles.budget}>
          <Ionicons name="cash-outline" size={16} color={colors.brandTertiary} />
          <Text style={styles.budgetText}>{item.budget}</Text>
        </View>
        <Pressable style={styles.viewButton}>
          <Text style={styles.viewButtonText}>
            Ver {item.quotes} {item.quotes === 1 ? "presupuesto" : "presupuestos"}
          </Text>
          <Ionicons name="arrow-forward" size={15} color={colors.onBrandPrimary} />
        </Pressable>
      </View>
      <View style={styles.notifiedRow}>
        <Ionicons name="paper-plane-outline" size={13} color={colors.muted} />
        <Text style={styles.notifiedText}>{item.notified}</Text>
      </View>
    </View>
  );
}

export default function RequestsPreview() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [selectedFilter, setSelectedFilter] = useState("Todas");

  return (
    <View style={styles.root}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: 28 }}
      >
        <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
          <View style={styles.topline}>
            <View style={styles.conceptBadge}>
              <View style={styles.conceptDot} />
              <Text style={styles.conceptText}>CONCEPTO</Text>
            </View>
            <Pressable accessibilityLabel="Notificaciones" style={styles.bell}>
              <Ionicons name="notifications-outline" size={21} color={colors.onSurface} />
              <View style={styles.notificationDot} />
            </Pressable>
          </View>

          <Text style={styles.title}>Mis solicitudes</Text>
          <View style={styles.locationRow}>
            <Ionicons name="location" size={15} color={colors.brandPrimary} />
            <Text style={styles.locationText}>Torino, Italia</Text>
            <Text style={styles.locationSeparator}>·</Text>
            <Text style={styles.changeLocation}>Tu zona</Text>
          </View>

          <Pressable style={styles.publishButton}>
            <Ionicons name="add" size={21} color={colors.onBrandPrimary} />
            <Text style={styles.publishButtonText}>Publicar un trabajo</Text>
          </Pressable>
        </View>

        <View style={styles.privacyCard}>
          <View style={styles.privacyIcon}>
            <Ionicons name="shield-checkmark" size={19} color={colors.onBrandSecondary} />
          </View>
          <View style={styles.privacyCopy}>
            <Text style={styles.privacyTitle}>Tu privacidad está protegida</Text>
            <Text style={styles.privacyDescription}>
              Los especialistas solo ven tu ciudad, las fotos y el trabajo que necesitas. Tu teléfono y dirección permanecen privados.
            </Text>
            <View style={styles.inAppReply}>
              <Ionicons name="chatbubble-ellipses-outline" size={13} color={colors.brandTertiary} />
              <Text style={styles.inAppReplyText}>Recibes presupuestos aquí, dentro de la app</Text>
            </View>
          </View>
        </View>

        <View style={styles.sectionHeading}>
          <View>
            <Text style={styles.sectionTitle}>Tus trabajos publicados</Text>
            <Text style={styles.sectionSub}>Recibe ofertas de especialistas cercanos</Text>
          </View>
          <View style={styles.newCount}>
            <Text style={styles.newCountText}>2 activas</Text>
          </View>
        </View>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.filters}
        >
          {["Todas", "Con presupuestos", "Esperando"].map((filter) => {
            const active = selectedFilter === filter;
            return (
              <Pressable
                key={filter}
                onPress={() => setSelectedFilter(filter)}
                style={[styles.filter, active && styles.filterActive]}
              >
                <Text style={[styles.filterText, active && styles.filterTextActive]}>{filter}</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        <View style={styles.feed}>
          {requests.map((item) => <RequestCard key={item.title} item={item} />)}
          <View style={styles.privacyNote}>
            <Ionicons name="shield-checkmark-outline" size={17} color={colors.brandTertiary} />
            <Text style={styles.privacyText}>Sin llamadas no solicitadas: los profesionales responden por la app.</Text>
          </View>
        </View>
      </ScrollView>

      <View style={[styles.tabBar, { paddingBottom: Math.max(insets.bottom, 8) }]}>
        <Tab icon="scan-outline" label="Escanear" />
        <Tab icon="document-text" label="Solicitudes" active />
        <Tab icon="people-outline" label="Expertos" />
        <Tab icon="storefront-outline" label="Tiendas" />
        <Tab icon="chatbubble-ellipses-outline" label="Mensajes" />
        <Tab icon="person-circle-outline" label="Perfil" />
      </View>
    </View>
  );
}

function Tab({ icon, label, active = false }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; active?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.tab}>
      <Ionicons name={icon} size={21} color={active ? colors.brandPrimary : colors.muted} />
      <Text numberOfLines={1} style={[styles.tabLabel, active && styles.tabLabelActive]}>{label}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 20, paddingBottom: 20, backgroundColor: c.surface },
  topline: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  conceptBadge: { flexDirection: "row", alignItems: "center", gap: 6, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: c.brandSecondary },
  conceptDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: c.brandPrimary },
  conceptText: { color: c.onBrandSecondary, fontSize: 10, fontWeight: "800", letterSpacing: 0.6 },
  bell: { width: 38, height: 38, borderRadius: 19, backgroundColor: c.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  notificationDot: { position: "absolute", right: 8, top: 8, width: 7, height: 7, borderRadius: 4, backgroundColor: c.brandPrimary, borderWidth: 1, borderColor: c.surfaceSecondary },
  title: { color: c.onSurface, fontFamily: fonts.display, fontSize: 27, letterSpacing: -0.5 },
  locationRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 6 },
  locationText: { color: c.onSurfaceTertiary, fontSize: 13, fontWeight: "600" },
  locationSeparator: { color: c.muted, fontSize: 14 },
  changeLocation: { color: c.brandTertiary, fontSize: 13, fontWeight: "600" },
  publishButton: { marginTop: 18, height: 48, borderRadius: 13, backgroundColor: c.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 },
  publishButtonText: { color: c.onBrandPrimary, fontSize: 15, fontWeight: "800" },
  privacyCard: { marginHorizontal: 16, marginTop: 2, marginBottom: 20, padding: 13, borderRadius: 15, backgroundColor: c.brandSecondary, flexDirection: "row", alignItems: "flex-start", gap: 10 },
  privacyIcon: { width: 34, height: 34, borderRadius: 11, backgroundColor: c.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  privacyCopy: { flex: 1, gap: 4 },
  privacyTitle: { color: c.onBrandSecondary, fontSize: 13, fontWeight: "800" },
  privacyDescription: { color: c.onSurfaceTertiary, fontSize: 11, lineHeight: 16 },
  inAppReply: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 3 },
  inAppReplyText: { color: c.brandTertiary, fontSize: 10, fontWeight: "700" },
  sectionHeading: { paddingHorizontal: 20, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 14 },
  sectionTitle: { color: c.onSurface, fontSize: 18, fontWeight: "800" },
  sectionSub: { color: c.muted, fontSize: 11, marginTop: 3 },
  newCount: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: 999, backgroundColor: c.brandSecondary },
  newCountText: { color: c.onBrandSecondary, fontSize: 10, fontWeight: "700" },
  filters: { paddingHorizontal: 20, gap: 8, paddingBottom: 14 },
  filter: { borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  filterActive: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  filterText: { color: c.onSurfaceTertiary, fontSize: 12, fontWeight: "600" },
  filterTextActive: { color: c.onSurfaceInverse },
  feed: { paddingHorizontal: 16, gap: 12 },
  card: { padding: 14, borderRadius: 18, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  cardMeta: { flexDirection: "row", alignItems: "center", gap: 6 },
  categoryIcon: { width: 27, height: 27, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  category: { color: c.onSurface, fontSize: 12, fontWeight: "700" },
  dot: { color: c.muted },
  age: { flex: 1, color: c.muted, fontSize: 11 },
  more: { width: 28, height: 28, alignItems: "center", justifyContent: "center" },
  cardTitle: { marginTop: 10, color: c.onSurface, fontFamily: fonts.display, fontSize: 19, letterSpacing: -0.2 },
  description: { marginTop: 4, marginBottom: 10, color: c.onSurfaceTertiary, fontSize: 12, lineHeight: 17 },
  photoWrap: { height: 142, borderRadius: 12, overflow: "hidden", backgroundColor: c.surfaceTertiary },
  photo: { width: "100%", height: "100%" },
  distance: { position: "absolute", top: 9, right: 9, flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, backgroundColor: c.scrim },
  distanceText: { color: c.onSurfaceInverse, fontSize: 10, fontWeight: "700" },
  photoCount: { position: "absolute", left: 9, bottom: 9, flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, backgroundColor: c.scrim },
  photoCountText: { color: c.onSurfaceInverse, fontSize: 10, fontWeight: "700" },
  quoteRow: { flexDirection: "row", alignItems: "center", gap: 9, marginTop: 12, marginBottom: 11 },
  avatars: { flexDirection: "row", alignItems: "center", paddingLeft: 1 },
  avatar: { width: 25, height: 25, borderWidth: 2, borderColor: c.surfaceSecondary, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  avatarText: { color: c.onSurfaceTertiary, fontSize: 7, fontWeight: "800" },
  quoteText: { color: c.onSurfaceTertiary, fontSize: 11 },
  quoteNumber: { color: c.onSurface, fontWeight: "800" },
  cardFooter: { paddingTop: 10, borderTopWidth: 1, borderTopColor: c.divider, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  budget: { flexDirection: "row", alignItems: "center", gap: 5, flex: 1 },
  budgetText: { color: c.brandTertiary, fontSize: 11, fontWeight: "700" },
  viewButton: { borderRadius: 9, backgroundColor: c.brandPrimary, paddingHorizontal: 11, paddingVertical: 8, flexDirection: "row", alignItems: "center", gap: 5 },
  viewButtonText: { color: c.onBrandPrimary, fontSize: 11, fontWeight: "800" },
  notifiedRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 9 },
  notifiedText: { color: c.muted, fontSize: 10 },
  privacyNote: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, padding: 12 },
  privacyText: { color: c.muted, fontSize: 10, flexShrink: 1 },
  tabBar: { backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border, flexDirection: "row", alignItems: "center", justifyContent: "space-around", paddingTop: 8 },
  tab: { flex: 1, minWidth: 0, alignItems: "center", gap: 3 },
  tabLabel: { color: c.muted, fontSize: 9, fontWeight: "600" },
  tabLabelActive: { color: c.brandPrimary, fontWeight: "800" },
}));
