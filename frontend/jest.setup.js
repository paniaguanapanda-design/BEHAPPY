/* global jest */
// Native modules have no implementation under Jest: use the official in-memory mocks.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);
