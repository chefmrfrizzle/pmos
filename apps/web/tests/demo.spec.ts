import {expect,test} from '@playwright/test'
test('public demo controls and routes work',async({page},testInfo)=>{
 await page.goto('/');await expect(page.getByRole('heading',{name:'Command Center'})).toBeVisible()
 if(testInfo.project.name==='mobile'){await page.getByRole('button',{name:'Open navigation'}).click();await expect(page.getByLabel('Primary navigation')).toBeVisible();await page.getByRole('button',{name:'Close navigation'}).click()}
 await page.getByRole('button',{name:'View data boundary'}).click();await expect(page.getByRole('dialog',{name:'The public / private boundary'})).toBeVisible();await page.getByRole('button',{name:'Close dialog'}).click()
 await page.getByRole('button',{name:'Explain ranking'}).click();await expect(page.getByRole('dialog',{name:/Northstar Collection/})).toContainText('Weighted result');await page.getByRole('button',{name:'Close drawer'}).click()
 await page.getByRole('button',{name:/Search/}).click();await page.getByPlaceholder(/Search assets/).fill('Bridgewater');await expect(page.getByRole('button',{name:/Bridgewater Associates/})).toBeVisible()
})
test('institution universe uses real public-source identities',async({page})=>{await page.goto('/universes');await expect(page.getByRole('heading',{name:'Institutional Universes'})).toBeVisible();await page.getByRole('button',{name:'Venture Capital',exact:true}).click();await expect(page.getByRole('heading',{name:'Sequoia Capital'})).toBeVisible();await expect(page.getByRole('link',{name:/Open official source/}).first()).toHaveAttribute('href',/^https:/)})
test('keyboard focus and dialog semantics are usable',async({page})=>{await page.goto('/');const boundary=page.getByRole('button',{name:'View data boundary'});await boundary.focus();await expect(boundary).toBeFocused();await page.keyboard.press('Enter');await expect(page.getByRole('dialog')).toHaveAttribute('aria-modal','true');await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0)})
