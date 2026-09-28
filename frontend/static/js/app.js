const $=id=>document.getElementById(id);
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const money=value=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(value);
const formatDateTime=value=>{const date=new Date(`${String(value).replace(' ','T')}Z`);return Number.isNaN(date.getTime())?String(value):new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(date)};
const api=async(url,opt={})=>{const r=await fetch(url,{headers:{'Content-Type':'application/json'},...opt});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.error||'Request failed');return d};
function initAuthForms(){
	$('loginForm')?.addEventListener('submit',event=>{event.preventDefault();login()});
	$('registerForm')?.addEventListener('submit',event=>{event.preventDefault();register()});
	document.querySelectorAll('[data-demo-email]').forEach(button=>button.addEventListener('click',()=>{
		$('email').value=button.dataset.demoEmail;
		$('password').value=button.dataset.demoPassword;
		$('password').focus();
	}));
}
async function login(){
	const button=$('loginSubmit');
	const message=$('msg');
	button.disabled=true;button.textContent='Signing in...';message.textContent='';
	try{const d=await api('/api/auth/login',{method:'POST',body:JSON.stringify({email:$('email').value,password:$('password').value})});location.href=d.role==='ADMIN'?'/admin':d.role==='STAFF'?'/staff':'/dashboard'}
	catch(e){message.textContent=e.message}
	finally{button.disabled=false;button.textContent='Sign in'}
}
async function register(){
	const button=$('registerSubmit');
	const message=$('msg');
	button.disabled=true;button.textContent='Creating account...';message.textContent='';
	try{await api('/api/auth/register',{method:'POST',body:JSON.stringify(Object.fromEntries(['full_name','student_id','email','phone','password','confirm_password'].map(x=>[x,$(x).value])))});message.textContent='Account created. You can now sign in.';$('registerForm').reset()}
	catch(e){message.textContent=e.message}
	finally{button.disabled=false;button.textContent='Create account'}
}
async function logout(){await api('/api/auth/logout',{method:'POST'}).catch(()=>{});location.href='/login'}
let cart=[];
let menuItems=[];
let knownNotificationIds=new Set();
let notificationHistoryLoaded=false;
let notificationToastTimer;

async function initDashboard(){
	try{
		const me=await api('/api/me');
		$('welcome').textContent='Welcome back, '+me.name;
		setupNotificationControls();
		const d=await api('/api/menu');
		menuItems=d.items;
		const categories=[...new Set(menuItems.map(item=>item.category))].sort();
		categories.forEach(category=>$('categoryFilter').add(new Option(category,category)));
		$('menuSearch').addEventListener('input',renderMenu);
		$('categoryFilter').addEventListener('change',renderMenu);
		$('menu').addEventListener('click',event=>{
			const button=event.target.closest('[data-add-id]');
			if(button)add(Number(button.dataset.addId));
		});
		restoreCart();
		renderMenu();
		refreshCart();
		await refreshNotifications();
		setInterval(()=>refreshNotifications(true).catch(()=>{}),15000);
	}catch(e){
		if(e.message==='Authentication required')location.href='/login';
		else showDashboardError(e);
	}
}

async function initOrders(){
	try{
		await api('/api/me');
		setupNotificationControls();
		const d=await api('/api/menu');
		menuItems=d.items;
		restoreCart();
		$('cart').addEventListener('click',event=>{
			const button=event.target.closest('[data-cart-action]');
			if(button)changeQuantity(Number(button.dataset.itemId),button.dataset.cartAction);
		});
		$('orders').addEventListener('click',event=>{
			const cancelButton=event.target.closest('[data-cancel-id]');
			if(cancelButton)cancelOrder(Number(cancelButton.dataset.cancelId));
		});
		refreshCart();
		await Promise.all([refreshOrders(),refreshQueue(),refreshNotifications(true)]);
		setInterval(()=>refreshOrders().catch(showDashboardError),10000);
		setInterval(()=>refreshQueue().catch(showDashboardError),10000);
		setInterval(()=>refreshNotifications(true).catch(()=>{}),15000);
	}catch(e){
		if(e.message==='Authentication required')location.href='/login';
		else showDashboardError(e);
	}
}

function setupNotificationControls(){
	$('openNotifications').addEventListener('click',openNotificationsDialog);
	$('openNotificationsFromToast').addEventListener('click',openNotificationsDialog);
	$('closeNotifications').addEventListener('click',()=>$('notificationsDialog').close());
	$('notificationsDialog').addEventListener('click',event=>{
		if(event.target===$('notificationsDialog'))$('notificationsDialog').close();
	});
	$('notifications').addEventListener('click',event=>{
		const button=event.target.closest('[data-read-id]');
		if(button)markNotificationRead(Number(button.dataset.readId));
	});
	$('dismissNotificationToast').addEventListener('click',hideNotificationToast);
}

function renderMenu(){
	const query=$('menuSearch').value.trim().toLocaleLowerCase();
	const category=$('categoryFilter').value;
	const items=menuItems.filter(item=>
		(!category||item.category===category)&&
		(!query||`${item.name} ${item.description||''}`.toLocaleLowerCase().includes(query))
	);
	$('menuCount').textContent=`${items.length} ${items.length===1?'dish':'dishes'}`;
	$('menu').innerHTML=items.length?items.map(item=>`<article class="food">
		<img class="food-image" src="${escapeHTML(item.image||'/static/images/meal-default.jpg')}" alt="${escapeHTML(item.name)}" loading="lazy">
		<span class="food-category">${escapeHTML(item.category)}</span>
		<h3>${escapeHTML(item.name)}</h3>
		<p>${escapeHTML(item.description||'Freshly prepared for you.')}</p>
		<div class="food-meta"><strong>${money(item.price)}</strong><span>${escapeHTML(item.preparation_time)} min</span></div>
		<button data-add-id="${Number(item.id)}" ${item.stock_quantity<1?'disabled':''}>${item.stock_quantity<1?'Sold out':'Add to order'}</button>
	</article>`).join(''):'<p class="empty-state">No dishes match your search.</p>';
}

function add(id){
	const item=menuItems.find(menuItem=>menuItem.id===id);
	if(!item||item.stock_quantity<1)return;
	const selected=cart.find(line=>line.id===id);
	if(selected){if(selected.quantity>=item.stock_quantity)return;selected.quantity++}
	else cart.push({id,name:item.name,price:item.price,quantity:1});
	if($('orderMsg'))$('orderMsg').textContent='';
	persistCart();
	refreshCart();
}

function restoreCart(){
	try{
		const saved=JSON.parse(localStorage.getItem('smartCanteenCart')||'[]');
		cart=saved.map(line=>{
			const item=menuItems.find(menuItem=>menuItem.id===Number(line.id));
			const quantity=Math.min(Math.floor(Number(line.quantity)),Number(item?.stock_quantity||0));
			return item&&quantity>0?{id:item.id,name:item.name,price:item.price,quantity}:null;
		}).filter(Boolean);
	}catch{cart=[]}
	persistCart();
}

function persistCart(){
	try{localStorage.setItem('smartCanteenCart',JSON.stringify(cart))}catch{}
}

function refreshCart(){
	const subtotal=cart.reduce((sum,item)=>sum+item.price*item.quantity,0);
	const totalQuantity=cart.reduce((sum,item)=>sum+item.quantity,0);
	if($('cartCount')){$('cartCount').hidden=totalQuantity===0;$('cartCount').textContent=totalQuantity>99?'99+':String(totalQuantity)}
	if(!$('cart'))return;
	$('cartTotal').textContent=money(subtotal);
	$('placeOrderButton').disabled=!cart.length;
	$('cart').innerHTML=cart.length?cart.map(item=>`<div class="cart-line">
		<div><strong>${escapeHTML(item.name)}</strong><span>${money(item.price)} each</span></div>
		<div class="quantity-control" aria-label="Quantity for ${escapeHTML(item.name)}">
			<button data-item-id="${item.id}" data-cart-action="decrease" aria-label="Decrease ${escapeHTML(item.name)} quantity">−</button>
			<span>${item.quantity}</span>
			<button data-item-id="${item.id}" data-cart-action="increase" aria-label="Increase ${escapeHTML(item.name)} quantity">+</button>
		</div>
	</div>`).join(''):'<p class="empty-state">Your basket is empty.</p>';
}

function changeQuantity(id,action){
	const line=cart.find(item=>item.id===id);
	if(!line)return;
	if(action==='decrease')line.quantity--;
	if(action==='increase'){
		const item=menuItems.find(menuItem=>menuItem.id===id);
		if(line.quantity<(item?.stock_quantity||0))line.quantity++;
	}
	cart=cart.filter(item=>item.quantity>0);
	persistCart();
	refreshCart();
}

async function placeOrder(){
	const button=$('placeOrderButton');
	if(!cart.length)return;
	button.disabled=true;
	button.textContent='Placing order...';
	try{
		const d=await api('/api/orders',{method:'POST',body:JSON.stringify({items:cart.map(({id,quantity})=>({id,quantity})),pickup_slot:'ASAP'})});
		cart=[];
		persistCart();
		refreshCart();
		$('orderMsg').textContent=`Order ${d.order_id} placed. Your token is #${d.token}.`;
		await Promise.all([refreshOrders(),refreshQueue(),refreshNotifications()]);
	}catch(e){$('orderMsg').textContent=e.message}
	finally{button.textContent='Place order';button.disabled=!cart.length}
}

async function refreshOrders(){
	const d=await api('/api/orders');
	$('orders').innerHTML=d.orders.length?d.orders.map(order=>`<article class="activity-row">
		<div><strong>${escapeHTML(order.public_order_id)}</strong><small class="order-date">${escapeHTML(formatDateTime(order.created_at))}</small><p>${escapeHTML(order.items)}</p></div>
		<div class="activity-meta">
			<strong>${money(order.total)}</strong>
			<span class="status status-${escapeHTML(order.status.toLowerCase().replaceAll('_','-'))}">${escapeHTML(order.status.replaceAll('_',' '))}</span>
			${['ORDER_PLACED','ACCEPTED','PREPARING'].includes(order.status)?`<button type="button" class="cancel-order" data-cancel-id="${Number(order.id)}">Cancel</button>`:''}
		</div>
	</article>`).join(''):'<p class="empty-state">Your orders will appear here.</p>';
}

async function cancelOrder(id){
	try{
		const d=await api(`/api/orders/${id}/cancel`,{method:'POST'});
		$('orderMsg').textContent=d.message;
		await Promise.all([refreshOrders(),refreshQueue(),refreshNotifications(true)]);
	}catch(e){$('orderMsg').textContent=e.message}
}

async function refreshQueue(){
	const d=await api('/api/queue/my-position');
	$('queue').innerHTML=d.token_number?`<div class="queue-ticket">
		<div><span>Your token</span><strong>#${escapeHTML(d.token_number)}</strong></div>
		<div><span>People ahead</span><strong>${escapeHTML(d.position)}</strong></div>
	</div><p class="queue-status">Current status <span class="status">${escapeHTML(d.status.replaceAll('_',' '))}</span></p>`:'<p class="empty-state">Your next order will show here.</p>';
}

async function refreshNotifications(notifyNew=false){
	const d=await api('/api/notifications');
	const newNotifications=d.notifications.filter(note=>!knownNotificationIds.has(Number(note.id)));
	d.notifications.forEach(note=>knownNotificationIds.add(Number(note.id)));
	if(notificationHistoryLoaded&&notifyNew&&newNotifications.length)showNotificationToast(newNotifications[0]);
	notificationHistoryLoaded=true;
	const unread=d.notifications.filter(note=>!note.is_read).length;
	const badge=$('unreadCount');
	badge.hidden=unread===0;
	badge.textContent=unread>99?'99+':String(unread);
	document.querySelector('.notification-shortcut').setAttribute('aria-label',`Notifications, ${unread} unread`);
	$('notifications').innerHTML=d.notifications.length?d.notifications.map(note=>`<article class="notification-row ${note.is_read?'is-read':''}">
		<div><strong>${escapeHTML(note.title)}</strong><p>${escapeHTML(note.message)}</p><small>${escapeHTML(note.created_at)}</small></div>
		${note.is_read?'':'<button data-read-id="'+Number(note.id)+'">Mark read</button>'}
	</article>`).join(''):'<p class="empty-state">Updates about your orders will appear here.</p>';
}

function showNotificationToast(note){
	$('notificationToastText').textContent=`${note.title}: ${note.message}`;
	$('notificationToast').classList.add('is-visible');
	$('notificationToast').setAttribute('aria-hidden','false');
	clearTimeout(notificationToastTimer);
	notificationToastTimer=setTimeout(hideNotificationToast,7000);
}

function openNotificationsDialog(){
	$('notificationsDialog').showModal();
}

function hideNotificationToast(){
	$('notificationToast').classList.remove('is-visible');
	$('notificationToast').setAttribute('aria-hidden','true');
}

async function markNotificationRead(id){
	try{await api(`/api/notifications/${id}/read`,{method:'PUT'});await refreshNotifications()}
	catch(e){$('notifications').insertAdjacentHTML('afterbegin',`<p class="feedback">${escapeHTML(e.message)}</p>`)}
}

function showDashboardError(error){
	const message=escapeHTML(error.message||'Something went wrong. Please try again.');
	['menu','queue','orders','notifications'].forEach(id=>{
		const element=$(id);
		if(element&&!element.dataset.loaded)element.innerHTML=`<p class="feedback">${message}</p>`;
	});
}

async function initStaff(){
	try{
		await api('/api/me');
		setupNotificationControls();
		await Promise.all([refreshStaff(),refreshNotifications()]);
		setInterval(()=>refreshStaff().catch(showDashboardError),5000);
		setInterval(()=>refreshNotifications(true).catch(()=>{}),10000);
	}catch(e){if(e.message==='Authentication required')location.href='/login';else showDashboardError(e)}
}
async function refreshStaff(){
	const d=await api('/api/staff/orders');
	$('staffOrders').innerHTML=d.orders.map(x=>`<article class="staff-order">
		<header><div><span class="ticket-number">#${escapeHTML(x.token_number)}</span><strong>${escapeHTML(x.public_order_id)}</strong></div><span class="status">${escapeHTML(x.status.replaceAll('_',' '))}</span></header>
		<p class="staff-customer">${escapeHTML(x.student)}</p><p class="staff-order-time">${escapeHTML(formatDateTime(x.created_at))}</p><p class="staff-items">${escapeHTML(x.items)}</p>
		<div class="staff-order-footer"><span>Order #${escapeHTML(x.id)}</span>${x.status==='ORDER_PLACED'?`<button onclick="setStatus(${Number(x.id)},'ACCEPTED')">Accept order</button>`:''}${x.status==='ACCEPTED'?`<button onclick="setStatus(${Number(x.id)},'PREPARING')">Start preparing</button>`:''}${x.status==='PREPARING'?`<button onclick="setStatus(${Number(x.id)},'READY')">Mark ready</button>`:''}${x.status==='READY'?`<button onclick="verify(${Number(x.id)})">Mark collected</button>`:''}</div>
	</article>`).join('')||'<p class="empty-state">No orders in the kitchen queue.</p>';
}
async function setStatus(id,status){await api('/api/staff/orders/'+id+'/status',{method:'PUT',body:JSON.stringify({status})});await Promise.all([refreshStaff(),refreshNotifications(true)])}
async function verify(id){await api('/api/staff/orders/'+id+'/verify',{method:'POST'});await Promise.all([refreshStaff(),refreshNotifications(true)])}
async function initAdmin(){
	try{
		await api('/api/me');
		const d=await api('/api/admin/analytics');
		$('stats').innerHTML=`<article class="stat-item"><span>Enrolled students</span><strong>${Number(d.students)}</strong></article><article class="stat-item"><span>Orders today</span><strong>${Number(d.today_orders)}</strong></article><article class="stat-item"><span>Today's revenue</span><strong>${money(d.revenue)}</strong></article><article class="stat-item"><span>Active queue</span><strong>${Number(d.active_queue)}</strong></article>`;
		const l=await api('/api/admin/audit-logs');
		$('logs').innerHTML=l.logs.length?l.logs.map(x=>`<article class="audit-row"><time>${escapeHTML(x.timestamp)}</time><strong>${escapeHTML(x.action.replaceAll('_',' '))}</strong><span>${escapeHTML(x.entity)} #${escapeHTML(x.entity_id)}</span><p>${escapeHTML(x.description)}</p></article>`).join(''):'<p class="empty-state">No recent activity.</p>';
	}catch(e){location.href='/login'}
}
