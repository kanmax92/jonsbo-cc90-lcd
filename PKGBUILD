# Maintainer: Kaness Kalaichelvan <kanmax92 on GitHub>
pkgname=jonsbo-cc90-lcd
pkgver=1.0.0
pkgrel=1
pkgdesc="Live CPU/GPU temperature display for the Jonsbo CC90 Digital cooler LCD (Linux daemon)"
arch=("any")
url="https://github.com/kanmax92/jonsbo-cc90-lcd"
license=("MIT")
depends=("python")
optdepends=("nvidia-utils: GPU temperature for the bar gauge")
source=("$pkgname-$pkgver.tar.gz::https://github.com/kanmax92/jonsbo-cc90-lcd/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=("SKIP")  # filled by updpkgsums after the release exists

package() {
  cd "$srcdir/$pkgname-$pkgver"
  local pysite="$(python3 -c 'import site; print(site.getsitepackages()[0])')"

  install -Dm755 cc90_lcd.py "$pkgdir/usr/bin/cc90-lcd"
  install -Dm644 pydes.py "$pkgdir$pysite/pydes.py"
  install -Dm644 udev/60-jonsbo-cc90.rules \
    "$pkgdir/usr/lib/udev/rules.d/60-jonsbo-cc90.rules"
  install -Dm644 systemd/cc90-lcd.service \
    "$pkgdir/usr/lib/systemd/user/cc90-lcd.service"
  install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
  install -Dm644 docs/PROTOCOL.md "$pkgdir/usr/share/doc/$pkgname/PROTOCOL.md"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
