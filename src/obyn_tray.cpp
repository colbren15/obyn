// SPDX-FileCopyrightText: 2026 Daniele Frasca
// SPDX-FileCopyrightText: 2026 OBYN contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Piccolo StatusNotifier KDE separato: nessuna dipendenza Python aggiuntiva.

#include <QApplication>
#include <QFile>
#include <QIcon>
#include <QMenu>
#include <QProcess>

#include <KStatusNotifierItem/KStatusNotifierItem>

int main(int argc, char *argv[]) {
    QApplication application(argc, argv);
    QString obynExecutable;
    QString quitFile;
    QString openLabel = QStringLiteral("Open OBYN");
    QString quitLabel = QStringLiteral("Quit OBYN");
    QString statusLabel = QStringLiteral("Bluetooth management active");
    const QStringList arguments = application.arguments();
    for (int index = 1; index + 1 < arguments.size(); ++index) {
        if (arguments.at(index) == QStringLiteral("--obyn-exec")) {
            obynExecutable = arguments.at(++index);
        } else if (arguments.at(index) == QStringLiteral("--open-label")) {
            openLabel = arguments.at(++index);
        } else if (arguments.at(index) == QStringLiteral("--quit-label")) {
            quitLabel = arguments.at(++index);
        } else if (arguments.at(index) == QStringLiteral("--status-label")) {
            statusLabel = arguments.at(++index);
        } else if (arguments.at(index) == QStringLiteral("--quit-file")) {
            quitFile = arguments.at(++index);
        }
    }

    KStatusNotifierItem tray(QStringLiteral("obyn"));
    tray.setStandardActionsEnabled(false);
    tray.setCategory(KStatusNotifierItem::ApplicationStatus);
    tray.setIconByName(QStringLiteral("io.obyn.Bluetooth-symbolic"));
    tray.setTitle(QStringLiteral("OBYN · Only Bluetooth You Need"));
    tray.setToolTip(QStringLiteral("io.obyn.Bluetooth-symbolic"), QStringLiteral("OBYN"),
                    statusLabel);
    tray.setStatus(KStatusNotifierItem::Active);

    auto *menu = new QMenu;
    auto *open = menu->addAction(QIcon::fromTheme(QStringLiteral("window-restore")), openLabel);
    auto *exit = menu->addAction(QIcon::fromTheme(QStringLiteral("application-exit")), quitLabel);
    tray.setContextMenu(menu);

    const auto showObyn = [&obynExecutable]() {
        if (!obynExecutable.isEmpty()) {
            QProcess::startDetached(obynExecutable);
        }
    };
    QObject::connect(open, &QAction::triggered, showObyn);
    QObject::connect(&tray, &KStatusNotifierItem::activateRequested,
                     [&showObyn](bool, const QPoint &) { showObyn(); });
    QObject::connect(exit, &QAction::triggered, [&application, &quitFile]() {
        if (!quitFile.isEmpty()) {
            QFile request(quitFile);
            if (request.open(QIODevice::WriteOnly)) {
                request.close();
            }
        }
        application.quit();
    });
    return application.exec();
}
