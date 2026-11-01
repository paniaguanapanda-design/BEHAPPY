import React, { useState } from "react";
import { Image, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import { makeStyles, useTheme, fonts } from "@/src/theme";

const trades = ["Todas", "Fontanería", "Pintura", "Electricidad"];

const jobs = [
  {
    trade: "Fontanería",
    tradeIcon: "water-outline" as const,
    title: "Fuga debajo del fregadero",
    description: "Gotea al abrir el grifo. Me gustaría repararlo esta semana.",
    city: "Torino",
    distance: "A 2,4 km",
    time: "Hace 12 min",
    photos: 2,
    image: { uri: "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Ceiling_water_damage.jpg/1280px-Ceiling_water_damage.jpg" },
    tint: "#E7F5F8",
    color: "#16758A",
    replies: 2,
  },
  {
    trade: "Pintura",
    tradeIcon: "color-palette-outline" as const,
    title: "Pintar el dormitorio",
    description: "Habitación de unos 16 m². Quiero cambiar el color y tapar algunos agujeros.",
    city: "Torino",
    distance: "A 5,1 km",
    time: "Hace 34 min",
    photos: 3,
    image: require("../assets/images/login-hero.jpg"),
    tint: "#FFF1E6",
    color: "#B9570A",
    replies: 1,
  },
  {
    trade: "Fontanería",
    tradeIcon: "water-outline" as const,
    title: "Instalar una ducha nueva",
    description: "Quiero sustituir la bañera por una ducha. Busco presupuesto y disponibilidad.",
    city: "Torino",
    distance: "A 7,6 km",
    time: "Hace 1 h",
    photos: 2,
    image: { uri: "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Ceiling_water_damage.jpg/1280px-Ceiling_water_damage.jpg" },
    tint: "#E7F5F8",
    color: "#16758A",
    replies: 0,
  },
];

export default function RequestsProPreview() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [selectedTrade, setSelectedTrade] = useState("Todas");
  const filteredJobs = selectedTrade === "Todas" ? jobs : jobs.filter((job) => job.trade === selectedTrade);

  return (
    <View style={styles.root}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 24 }}>
        <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
          <View style={styles.topline}>
            <View style={styles.conceptBadge}>
              <View style={styles.conceptDot} />
              <Text style={styles.conceptText}>VISTA ESPECIALISTA · CONCEPTO</Text>
            </View>
            <Pressable accessibilityLabel="Notificaciones" style={styles.bell}>
              <Ionicons name="notifications-outline" size={21} color={colors.onSurface} />
              <View style={styles.notificationDot} />
            </Pressable>
          </View>
          <Text style={styles.title}>Solicitudes cerca</Text>
          <Text style={styles.subtitle}>Nuevos trabajos de clientes de tu zona</Text>

          <View style={styles.zoneCard}>
            <View style={styles.zoneIcon}>
              <Ionicons name="location" size={18} color={colors.onBrandPrimary} />
            </View>
            <View style={styles.zoneCopy}>
              <Text style={styles.zoneTitle}>Torino · radio de 8 km</Text>
              <Text style={styles.zoneNote}>Dentro de tu zona de trabajo configurada</Text>
            </View>
            <Pressable style={styles.adjustButton}>
              <Text style={styles.adjustText}>Ajustar</Text>
            </Pressable>
          </View>

          <View style={styles.matchRow}>
            <View style={styles.matchIcon}>
              <Ionicons name="checkmark-circle" size={17} color={colors.success} />
            </View>
            <Text style={styles.matchText}>Solo solicitudes de tus oficios y dentro de tu zona</Text>
          </View>
        </View>

        <View style={styles.feedHeader}>
          <View>
            <Text style={styles.feedTitle}>Disponibles para cotizar</Text>
            <Text style={styles.feedSubtitle}>{filteredJobs.length} solicitudes activas cerca de ti</Text>
          </View>
          <Pressable style={styles.sortButton}>
            <Ionicons name="options-outline" size={17} color={colors.onSurfaceTertiary} />
            <Text style={styles.sortText}>Filtrar</Text>
          </Pressable>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
          {trades.map((trade) => {
            const active = selectedTrade === trade;
            return (
              <Pressable
                key={trade}
                onPress={() => setSelectedTrade(trade)}
                style={[styles.filter, active && styles.filterActive]}
              >
                <Text style={[styles.filterText, active && styles.filterTextActive]}>{trade}</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        <View style={styles.feed}>
          {filteredJobs.map((job) => (
            <View key={job.title} style={styles.jobCard}>
              <View style={styles.jobMeta}>
                <View style={[styles.tradeIcon, { backgroundColor: job.tint }]}>
                  <Ionicons name={job.tradeIcon} size={16} color={job.color} />
                </View>
                <Text style={styles.tradeName}>{job.trade}</Text>
                <Text style={styles.metaDot}>·</Text>
                <Text style={styles.jobTime}>{job.time}</Text>
                <View style={styles.distancePill}>
                  <Ionicons name="navigate-outline" size={12} color={colors.brandTertiary} />
                  <Text style={styles.distanceText}>{job.distance}</Text>
                </View>
              </View>

              <Text style={styles.jobTitle}>{job.title}</Text>
              <Text style={styles.jobDescription}>{job.description}</Text>

              <View style={styles.jobPhotoWrap}>
                <Image source={job.image} style={styles.jobPhoto} resizeMode="cover" />
                <View style={styles.photoBadge}>
                  <Ionicons name="images-outline" size={13} color={colors.onSurfaceInverse} />
                  <Text style={styles.photoBadgeText}>{job.photos} fotos</Text>
                </View>
                <View style={styles.cityBadge}>
                  <Ionicons name="location" size={12} color={colors.onSurfaceInverse} />
                  <Text style={styles.cityText}>{job.city} · zona aproximada</Text>
                </View>
              </View>

              <View style={styles.customerRow}>
                <View style={styles.customerAvatar}>
                  <Ionicons name="person" size={15} color={colors.brandTertiary} />
                </View>
                <View style={styles.customerCopy}>
                  <Text style={styles.customerName}>Cliente verificado</Text>
                  <Text style={styles.customerPrivacy}>Teléfono y dirección privados</Text>
                </View>
                {job.replies > 0 ? (
                  <View style={styles.replyCount}>
                    <Text style={styles.replyCountText}>{job.replies} ofertas</Text>
                  </View>
                ) : (
                  <View style={styles.firstReply}>
                    <Text style={styles.firstReplyText}>Sé el primero</Text>
                  </View>
                )}
              </View>

              <Pressable style={styles.quoteButton}>
                <Ionicons name="paper-plane-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.quoteButtonText}>Enviar presupuesto</Text>
              </Pressable>
            </View>
          ))}
        </View>

        <View style={styles.privacyNote}>
          <Ionicons name="shield-checkmark-outline" size={16} color={colors.brandTertiary} />
          <Text style={styles.privacyText}>La conversación y el presupuesto se envían dentro de BeHappy.</Text>
        </View>
      </ScrollView>

      <View style={[styles.tabBar, { paddingBottom: Math.max(insets.bottom, 8) }]}>
        <Tab icon="grid-outline" label="Panel" />
        <Tab icon="document-text" label="Solicitudes" active />
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
      <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{label}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: 20, paddingBottom: 14 },
  topline: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  conceptBadge: { flexDirection: "row", alignItems: "center", gap: 6, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: c.brandSecondary },
  conceptDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: c.brandPrimary },
  conceptText: { color: c.onBrandSecondary, fontSize: 9, fontWeight: "800", letterSpacing: 0.45 },
  bell: { width: 38, height: 38, borderRadius: 19, backgroundColor: c.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  notificationDot: { position: "absolute", right: 8, top: 8, width: 7, height: 7, borderRadius: 4, backgroundColor: c.brandPrimary, borderWidth: 1, borderColor: c.surfaceSecondary },
  title: { color: c.onSurface, fontFamily: fonts.display, fontSize: 27, letterSpacing: -0.5 },
  subtitle: { marginTop: 3, color: c.muted, fontSize: 12 },
  zoneCard: { marginTop: 16, padding: 11, backgroundColor: c.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: c.border, flexDirection: "row", alignItems: "center", gap: 9 },
  zoneIcon: { width: 34, height: 34, borderRadius: 11, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  zoneCopy: { flex: 1 },
  zoneTitle: { color: c.onSurface, fontSize: 12, fontWeight: "800" },
  zoneNote: { marginTop: 3, color: c.muted, fontSize: 9 },
  adjustButton: { paddingHorizontal: 9, paddingVertical: 7, borderRadius: 8, backgroundColor: c.surfaceTertiary },
  adjustText: { color: c.brandTertiary, fontSize: 10, fontWeight: "700" },
  matchRow: { marginTop: 10, flexDirection: "row", alignItems: "center", gap: 6 },
  matchIcon: { width: 20, alignItems: "center" },
  matchText: { color: c.onSurfaceTertiary, fontSize: 10, fontWeight: "600" },
  feedHeader: { paddingHorizontal: 20, marginTop: 8, marginBottom: 12, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  feedTitle: { color: c.onSurface, fontSize: 18, fontWeight: "800" },
  feedSubtitle: { marginTop: 3, color: c.muted, fontSize: 10 },
  sortButton: { paddingHorizontal: 10, paddingVertical: 7, backgroundColor: c.surfaceSecondary, borderRadius: 9, borderWidth: 1, borderColor: c.border, flexDirection: "row", alignItems: "center", gap: 5 },
  sortText: { color: c.onSurfaceTertiary, fontSize: 10, fontWeight: "700" },
  filters: { paddingHorizontal: 20, gap: 8, paddingBottom: 12 },
  filter: { borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, borderRadius: 999, paddingHorizontal: 13, paddingVertical: 7 },
  filterActive: { backgroundColor: c.surfaceInverse, borderColor: c.surfaceInverse },
  filterText: { color: c.onSurfaceTertiary, fontSize: 11, fontWeight: "600" },
  filterTextActive: { color: c.onSurfaceInverse },
  feed: { paddingHorizontal: 15, gap: 11 },
  jobCard: { padding: 13, borderRadius: 17, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  jobMeta: { flexDirection: "row", alignItems: "center", gap: 6 },
  tradeIcon: { width: 26, height: 26, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  tradeName: { color: c.onSurface, fontSize: 11, fontWeight: "700" },
  metaDot: { color: c.muted },
  jobTime: { flex: 1, color: c.muted, fontSize: 10 },
  distancePill: { flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 7, paddingVertical: 5, borderRadius: 999, backgroundColor: c.brandSecondary },
  distanceText: { color: c.onBrandSecondary, fontSize: 9, fontWeight: "700" },
  jobTitle: { marginTop: 9, color: c.onSurface, fontFamily: fonts.display, fontSize: 18 },
  jobDescription: { marginTop: 3, marginBottom: 9, color: c.onSurfaceTertiary, fontSize: 11, lineHeight: 16 },
  jobPhotoWrap: { height: 122, borderRadius: 11, overflow: "hidden", backgroundColor: c.surfaceTertiary },
  jobPhoto: { width: "100%", height: "100%" },
  photoBadge: { position: "absolute", left: 8, bottom: 8, flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 7, paddingVertical: 5, borderRadius: 999, backgroundColor: c.scrim },
  photoBadgeText: { color: c.onSurfaceInverse, fontSize: 9, fontWeight: "700" },
  cityBadge: { position: "absolute", right: 8, bottom: 8, flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 7, paddingVertical: 5, borderRadius: 999, backgroundColor: c.scrim },
  cityText: { color: c.onSurfaceInverse, fontSize: 9, fontWeight: "700" },
  customerRow: { marginTop: 10, flexDirection: "row", alignItems: "center", gap: 8 },
  customerAvatar: { width: 30, height: 30, borderRadius: 15, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  customerCopy: { flex: 1 },
  customerName: { color: c.onSurface, fontSize: 10, fontWeight: "700" },
  customerPrivacy: { marginTop: 2, color: c.muted, fontSize: 9 },
  replyCount: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, backgroundColor: c.surfaceTertiary },
  replyCountText: { color: c.onSurfaceTertiary, fontSize: 9, fontWeight: "700" },
  firstReply: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, backgroundColor: "#EAF7EF" },
  firstReplyText: { color: "#267044", fontSize: 9, fontWeight: "700" },
  quoteButton: { marginTop: 11, height: 39, borderRadius: 10, backgroundColor: c.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 },
  quoteButtonText: { color: c.onBrandPrimary, fontSize: 12, fontWeight: "800" },
  privacyNote: { marginHorizontal: 18, marginTop: 14, padding: 11, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  privacyText: { color: c.muted, fontSize: 9, flexShrink: 1 },
  tabBar: { backgroundColor: c.surfaceSecondary, borderTopWidth: 1, borderTopColor: c.border, flexDirection: "row", alignItems: "center", justifyContent: "space-around", paddingTop: 8 },
  tab: { flex: 1, alignItems: "center", gap: 3 },
  tabLabel: { color: c.muted, fontSize: 9, fontWeight: "600" },
  tabLabelActive: { color: c.brandPrimary, fontWeight: "800" },
}));
